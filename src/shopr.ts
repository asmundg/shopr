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
}

interface Scores {
  [key: string]: number | undefined;
}

const DEFAULT_SCORE = 1000;
const UNSORTED_TAG = " [unsorted]";
const UNSORTED_RE = /\[unsorted\]/g;
const FLUFF_RE = /\d /g;

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

function lookupName(name: string): string {
  return name.toLowerCase().replace(UNSORTED_RE, "").replace(FLUFF_RE, "");
}

function lookup(scores: Scores, name: string): number {
  return scores[lookupName(name)] ?? DEFAULT_SCORE;
}

function update(scores: Scores, name: string, score: number): void {
  scores[lookupName(name)] = score;
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
          if (scores[lookupName(checklistItem.name)] == undefined) {
            logger(`Unknown item ${checklistItem.name}`);
          }

          await client.updateChecklistItem(
            card.id,
            idChecklist,
            checklistItem.id,
            {
              ...checklistItem,
              name:
                scores[lookupName(checklistItem.name)] != undefined ||
                checklistItem.name.match(UNSORTED_RE)
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
}

main();
