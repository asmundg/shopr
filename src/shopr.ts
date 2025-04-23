import * as fs from "fs";
import Axios from "axios";
import EloRank from "elo-rank";
import debug from "debug";
import "axios-debug-log";

const logger = debug("shopr:trelloClient");

import { trello, Checklist, TrelloClient } from "./trello";

interface Prefs {
  token: string;
  key: string;
  board: string;
  trainLabel: string;
  orderLabel: string;
  populateLabel: string;
  availableList: string;
  selectedList: string;
}

interface Scores {
  [key: string]: number | undefined;
}

const DEFAULT_SCORE = 1000;
const UNSORTED_TAG = " [unsorted]";
const UNSORTED_RE = /\[unsorted\]/g;

// Get trello client
function client(prefs: Prefs): TrelloClient {
  return trello({
    key: prefs.key,
    token: prefs.token,
    // fixme force put as application/json and not formencoded
    makeRequest: async (method, url, params, data) => {
      try {
        return (await Axios.request({ method, url, params, data })).data;
      } catch (err) {
        logger(err?.response?.data);
        throw err;
      }
    },
  });
}

// Get list of checklists to train on
async function trainSet(
  client: TrelloClient,
  prefs: Prefs
): Promise<Checklist[]> {
  const cards = await client.getBoardCards(prefs.board);
  const trainCheklistIds = cards.reduce<string[]>(
    (acc, card) =>
      card.labels.find((l) => l.name === prefs.trainLabel)
        ? [...acc, ...card.idChecklists]
        : acc,
    []
  );

  let trainChecklists: Checklist[] = [];
  for (const t of trainCheklistIds) {
    trainChecklists = [...trainChecklists, await client.getChecklist(t)];
  }

  return trainChecklists;
}

// Remove training label from cards containing given checklists
async function resetLabel(
  client: TrelloClient,
  labelName: string,
  idCards: string[]
): Promise<void> {
  for (const idCard of idCards) {
    const card = await client.getCard(idCard);
    await Promise.all(
      card.labels
        .reduce<string[]>(
          (acc, label) => (label.name === labelName ? [...acc, label.id] : acc),
          []
        )
        .map((idLabel) => client.removeLabel(card.id, idLabel))
    );
  }
}

// Strip completely useless stuff, like the unsorted tag and
// numbers. Then break into words and return an array of candidates
// for the item identifier.
function lookupCandidates(name: string): string[] {
  const stripped = name
    .toLowerCase()
    .replace(UNSORTED_RE, "")
    .replace(/[\d\(\)]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  const candidates = stripped.split(" ").sort();
  logger(`Lookup ${name} => ${candidates}`);
  return candidates;
}

function lookup(scores: Scores, name: string): number {
  const candidates = lookupCandidates(name);

  // Use longest word as preferred identifier, if we don't find an
  // exact match. This is not the best heuristic. It would be useful
  // to be able to strip off adjectives and concentrate on nouns.
  const candidate = [candidates.join(","), ...candidates]
    .filter((c) => !!scores[c])
    .reduce(
      (leader, candidate) =>
        candidate.length > leader.length ? candidate : leader,
      ""
    );
  logger(`Lookup ${name} => final candidate ${candidate}`);
  return scores[candidate] ?? DEFAULT_SCORE;
}

function update(scores: Scores, name: string, score: number): void {
  const candidates = lookupCandidates(name);
  // Save the score for all words in the item, as well as the full
  // string. This will cause us to score some irrelevant words, but
  // should provide a better chance of reusing knowledge when looking
  // for variations on the same thing (e.g. "beans" in "beans,white"
  // and "beans","green" (yes, the adjectives here are the same length
  // and can therefore be selected when we don't have the full string
  // in the score list)).
  [candidates.join(","), ...candidates].forEach((c) => (scores[c] = score));
}

// Order list according to score
async function orderList(
  client: TrelloClient,
  scores: Scores,
  prefs: Prefs
): Promise<void> {
  const cards = await client.getBoardCards(prefs.board);
  for (const card of cards) {
    if (!card.labels.find((l) => l.name === prefs.orderLabel)) {
      continue;
    }

    logger(`Ordering ${card.name}`);
    for (const idChecklist of card.idChecklists) {
      const checklist = await client.getChecklist(idChecklist);

      for (const checklistItem of checklist.checkItems) {
        logger(checklistItem);
        // Avoid negative pos values
        const pos = lookup(scores, checklistItem.name) + 100000;
        if (checklistItem.pos != pos) {
          await client.updateChecklistItem(
            card.id,
            idChecklist,
            checklistItem.id,
            {
              ...checklistItem,
              name:
                scores[lookupCandidates(checklistItem.name).join(",")] !=
                  undefined || checklistItem.name.match(UNSORTED_RE)
                  ? checklistItem.name
                  : `${checklistItem.name}${UNSORTED_TAG}`,
              pos,
            }
          );
        }
      }
    }
    logger(`Ordering ${card.name} done`);

    await resetLabel(client, prefs.orderLabel, [card.id]);
  }
}

// Populate shopping list from selected recipes
async function populateShoppingList(
  client: TrelloClient,
  prefs: Prefs
): Promise<void> {
  // Get all cards on the board
  const cards = await client.getBoardCards(prefs.board);
  
  // Find cards with the populate label
  for (const card of cards) {
    if (!card.labels.find((l) => l.name === prefs.populateLabel)) {
      continue;
    }

    logger(`Populating shopping list from ${card.name}`);
    
    // Get cards from the selected recipes list
    const selectedRecipes = await client.getListCards(prefs.selectedList);
    logger(`Found ${selectedRecipes.length} selected recipes`);
    
    // Keep track of items we've already added to avoid duplicates
    const addedItems = new Set<string>();
    
    // Get or create a checklist on the populate card
    let targetChecklistId: string;
    if (card.idChecklists.length === 0) {
      // Create a new checklist if one doesn't exist
      logger(`Creating new checklist on card ${card.name}`);
      const newChecklist = await client.createChecklist(card.id, "Shopping List");
      targetChecklistId = newChecklist.id;
    } else {
      // Use the first existing checklist
      targetChecklistId = card.idChecklists[0];
    }
    
    // For each recipe card in the selected list
    for (const recipeCard of selectedRecipes) {
      logger(`Processing recipe: ${recipeCard.name}`);
      
      // Get all checklists on the recipe card
      for (const idChecklist of recipeCard.idChecklists) {
        const checklist = await client.getChecklist(idChecklist);
        
        // Copy each item from the recipe checklist to the populate card's checklist
        for (const checklistItem of checklist.checkItems) {
          // Skip if we've already added this item (prevent duplicates)
          if (addedItems.has(checklistItem.name.toLowerCase())) {
            logger(`Skipping duplicate item: ${checklistItem.name}`);
            continue;
          }
          
          // Add the item to the populate card's checklist
          await client.addChecklistItem(targetChecklistId, checklistItem.name);
          addedItems.add(checklistItem.name.toLowerCase());
          logger(`Added item: ${checklistItem.name}`);
        }
      }
      
      // Move the recipe card back to the available recipes list
      await client.moveCardToList(recipeCard.id, prefs.availableList);
      logger(`Moved recipe ${recipeCard.name} back to available list`);
    }
    
    // Remove the populate label when done
    await resetLabel(client, prefs.populateLabel, [card.id]);
    logger(`Populating ${card.name} done`);
  }
}

// Utility function to print all lists on a board
async function listBoardLists(client: TrelloClient, prefs: Prefs): Promise<void> {
  try {
    const lists = await client.getBoardLists(prefs.board);
    console.log("Available lists on your board:");
    console.log(JSON.stringify(lists, null, 2));
  } catch (error) {
    console.error("Error fetching board lists:", error);
  }
}

function train(list: Checklist, oldScores: Readonly<Scores>): Scores {
  logger(`Training on ${list.checkItems.length} items`);
  var elo = new EloRank();

  const scores: Scores = { ...oldScores };

  list.checkItems.forEach((current) => {
    const currentScore = lookup(scores, current.name);
    list.checkItems.forEach((compare) => {
      // Same object
      if (current.pos === compare.pos) {
        return;
      }

      // Lower score means earlier in the sequence, to match Trello's
      // ordering
      const compareScore = lookup(scores, compare.name);
      update(
        scores,
        current.name,
        elo.updateRating(
          elo.getExpected(currentScore, compareScore),
          current.pos < compare.pos ? 0 : 1,
          currentScore
        )
      );
      update(
        scores,
        compare.name,
        elo.updateRating(
          elo.getExpected(compareScore, currentScore),
          compare.pos < current.pos ? 0 : 1,
          compareScore
        )
      );
    });
  });

  return scores;
}

async function main() {
  const prefs = JSON.parse(fs.readFileSync(".trello.json", "utf-8")) as Prefs;
  const c = client(prefs);
  
  // Check for command line arguments
  if (process.argv.includes("--list-ids")) {
    await listBoardLists(c, prefs);
    return;
  }
  
  const checkLists = await trainSet(c, prefs);

  const scores = fs.existsSync("scores.json")
    ? JSON.parse(fs.readFileSync("scores.json", "utf-8"))
    : {};
  const newScores = checkLists.reduce<Scores>(
    (scores, checkList) => train(checkList, scores),
    scores
  );
  fs.writeFileSync("scores.json", JSON.stringify(newScores));

  await resetLabel(
    c,
    prefs.trainLabel,
    checkLists.map((c) => c.idCard)
  );
  await orderList(c, scores, prefs);
  await populateShoppingList(c, prefs);
}

main();
