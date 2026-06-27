"""Main shopr application logic."""

import asyncio
import json
import logging
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from .elo import EloRank
from .trello import (
    Checklist,
    ChecklistItem,
    TrelloClient,
)


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(name)s: %(message)s'
)
logger = logging.getLogger("shopr:trelloClient")


# Constants
DEFAULT_SCORE = 1000.0
UNSORTED_TAG = " [unsorted]"
UNSORTED_RE = re.compile(r"\[unsorted\]")

# Units of measure that trail a quantity (e.g. "2L", "500 g"). Stripped
# together with the number so a stray unit letter doesn't survive as its
# own candidate word and bleed into unrelated items.
UNIT_RE = re.compile(
    r"\d+(?:\.\d+)?\s*("
    r"kg|kilograms?|g|grams?|lbs?|pounds?|oz|ounces?"
    r"|ml|milliliters?|millilitres?|l|liters?|litres?"
    r"|pkg|packs?|ct|count|x"
    r")\b"
)

# Descriptors and packaging words that don't identify the item itself.
# Leaving these in candidates causes both misses (the same item recorded
# with/without a descriptor produces different full keys) and bleed
# (unrelated items sharing a descriptor overwrite each other's fallback
# word score, e.g. "fresh basil" and "fresh cilantro" both producing "fresh").
STOPWORDS = {
    "fresh", "frozen", "organic", "large", "small", "medium", "extra",
    "chopped", "diced", "sliced", "minced", "ground", "raw", "ripe",
    "fine", "coarse", "can", "cans", "bag", "bags", "box", "boxes",
    "jar", "jars", "bunch", "bunches", "pack", "packs", "package",
    "packages", "container", "containers", "bottle", "bottles",
    "of", "and", "the", "a", "an", "for", "with",
}


# Type alias for scores
Scores = defaultdict[str, float]


def make_scores(data: dict[str, float] | None = None) -> Scores:
    """Create a scores defaultdict with DEFAULT_SCORE as default."""
    scores: Scores = defaultdict(lambda: DEFAULT_SCORE)
    if data:
        scores.update(data)
    return scores


class Prefs:
    """Preferences for shopr."""

    def __init__(self, data: dict[str, Any]):
        """Initialize preferences from dictionary."""
        self.token: str = data["token"]
        self.key: str = data["key"]
        self.board: str = data["board"]
        self.train_label: str = data["trainLabel"]
        self.order_label: str = data["orderLabel"]
        self.populate_label: str = data["populateLabel"]
        self.available_list: str = data["availableList"]
        self.selected_list: str = data["selectedList"]



def create_client(prefs: Prefs) -> TrelloClient:
    """Create a Trello client from preferences.

    Args:
        prefs: Preferences containing API credentials

    Returns:
        TrelloClient instance
    """
    return TrelloClient(key=prefs.key, token=prefs.token)


async def get_train_set(
    client: TrelloClient,
    prefs: Prefs,
) -> list[Checklist]:
    """Get list of checklists to train on.

    Args:
        client: Trello client
        prefs: Preferences

    Returns:
        List of checklists marked for training
    """
    cards = await client.get_board_cards(prefs.board)
    train_checklist_ids: list[str] = []

    for card in cards:
        # Check if card has the train label
        has_train_label = any(
            label.get("name") == prefs.train_label
            for label in card.labels
        )
        if has_train_label:
            train_checklist_ids.extend(card.idChecklists)

    train_checklists: list[Checklist] = []
    for checklist_id in train_checklist_ids:
        checklist = await client.get_checklist(checklist_id)
        train_checklists.append(checklist)

    return train_checklists


async def reset_label(
    client: TrelloClient,
    label_name: str,
    id_cards: list[str],
) -> None:
    """Remove label from cards.

    Args:
        client: Trello client
        label_name: Name of label to remove
        id_cards: List of card IDs
    """
    for id_card in id_cards:
        card = await client.get_card(id_card)
        for label in card.labels:
            if label.get("name") == label_name:
                await client.remove_label(card.id, label["id"])


def singularize(word: str) -> str:
    """Strip a common English plural suffix from a word.

    Best-effort heuristic, not a full stemmer: it exists to make
    "tomato"/"tomatoes" or "egg"/"eggs" resolve to the same candidate
    instead of being treated as unrelated items.

    Args:
        word: Word to singularize

    Returns:
        Singularized word
    """
    if len(word) <= 3:
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "zes", "ches", "shes", "oes")):
        return word[:-2]
    # Words ending in "us"/"ss" (asparagus, hummus, swiss) aren't plurals.
    if word.endswith(("us", "ss")):
        return word
    if word.endswith("s"):
        return word[:-1]
    return word


def lookup_candidates(name: str) -> list[str]:
    """Strip useless characters and return candidate identifiers.

    Args:
        name: Item name

    Returns:
        List of candidate identifiers
    """
    # Remove unsorted tag
    stripped = name.lower().replace("[unsorted]", "")
    # Remove quantity + unit combos (e.g. "2l", "500 g") so a stray unit
    # letter doesn't survive as its own candidate
    stripped = UNIT_RE.sub(" ", stripped)
    # Treat remaining punctuation as word separators
    stripped = re.sub(r"[\d\(\),.\-/&:;%]", " ", stripped)
    # Normalize whitespace
    stripped = re.sub(r"\s+", " ", stripped).strip()

    words = [word for word in stripped.split(" ") if word]
    words = [singularize(word) for word in words if word not in STOPWORDS]

    candidates = sorted(words)
    logger.debug(f"Lookup {name} => {candidates}")
    return candidates


def lookup(scores: Scores, name: str) -> float:
    """Look up score for an item name.

    Args:
        scores: Score storage
        name: Item name

    Returns:
        Score for the item
    """
    candidates = lookup_candidates(name)
    if not candidates:
        return DEFAULT_SCORE

    full_key = ",".join(candidates)
    if full_key in scores:
        return scores[full_key]

    # No exact match. Look for the known item whose words overlap the most
    # (by Jaccard similarity) rather than just any single shared word - a
    # single shared word (e.g. "chicken" in both "chicken broth" and
    # "chicken thighs") is a weak, bleed-prone signal on its own.
    query_words = set(candidates)
    best_key = None
    best_similarity = 0.0
    for key in scores:
        if "," not in key:
            continue
        key_words = set(key.split(","))
        overlap = query_words & key_words
        if not overlap:
            continue
        similarity = len(overlap) / len(query_words | key_words)
        if similarity > best_similarity:
            best_similarity = similarity
            best_key = key

    if best_key is not None:
        logger.debug(f"Lookup {name} => best overlap candidate {best_key}")
        return scores[best_key]

    # Last resort: fall back to the longest single word with a score.
    scored_words = [c for c in candidates if c in scores]
    if not scored_words:
        return DEFAULT_SCORE

    candidate = max(scored_words, key=len)
    logger.debug(f"Lookup {name} => final candidate {candidate}")
    return scores[candidate]


def update(scores: Scores, name: str, score: float) -> None:
    """Update score for an item name.

    Args:
        scores: Score storage
        name: Item name
        score: New score
    """
    candidates = lookup_candidates(name)
    # Save score for all words in the item, as well as the full string
    full_key = ",".join(candidates)
    for candidate in [full_key] + candidates:
        scores[candidate] = score


async def order_list(
    client: TrelloClient,
    scores: Scores,
    prefs: Prefs,
) -> None:
    """Order list according to scores.

    Args:
        client: Trello client
        scores: Score storage
        prefs: Preferences
    """
    cards = await client.get_board_cards(prefs.board)

    for card in cards:
        # Check if card has the order label
        has_order_label = any(
            label.get("name") == prefs.order_label
            for label in card.labels
        )
        if not has_order_label:
            continue

        logger.info(f"Ordering {card.name}")

        for id_checklist in card.idChecklists:
            checklist = await client.get_checklist(id_checklist)

            for checklist_item in checklist.checkItems:
                logger.debug(f"Processing item: {checklist_item.name}")
                # Avoid negative pos values
                pos = int(lookup(scores, checklist_item.name) + 100000)

                if checklist_item.pos != pos:
                    # Determine if item should have unsorted tag
                    candidates = lookup_candidates(checklist_item.name)
                    full_key = ",".join(candidates)
                    has_score = full_key in scores
                    has_unsorted_tag = bool(UNSORTED_RE.search(checklist_item.name))

                    new_name = checklist_item.name
                    if not has_score and not has_unsorted_tag:
                        new_name = f"{checklist_item.name}{UNSORTED_TAG}"

                    # Create updated checklist item
                    updated_item = ChecklistItem(
                        id=checklist_item.id,
                        idChecklist=checklist_item.idChecklist,
                        name=new_name,
                        pos=pos,
                        state=checklist_item.state,
                    )

                    await client.update_checklist_item(
                        card.id,
                        id_checklist,
                        checklist_item.id,
                        updated_item,
                    )

        logger.info(f"Ordering {card.name} done")
        await reset_label(client, prefs.order_label, [card.id])


def parse_item_quantity(item_name: str) -> tuple[str, int]:
    """Parse an item name to extract base name and quantity.

    Examples:
        "eggs" -> ("eggs", 1)
        "eggs 2" -> ("eggs", 2)
        "milk 3" -> ("milk", 3)

    Args:
        item_name: The item name, optionally with quantity at the end

    Returns:
        Tuple of (base_name, quantity)
    """
    parts = item_name.strip().rsplit(maxsplit=1)

    if len(parts) == 2 and parts[1].isdigit():
        return (parts[0], int(parts[1]))

    return (item_name.strip(), 1)


def format_item_with_quantity(base_name: str, quantity: int) -> str:
    """Format an item name with quantity.

    Args:
        base_name: The base item name
        quantity: The quantity

    Returns:
        Formatted item name (e.g., "eggs 3" if quantity > 1, "eggs" if quantity == 1)
    """
    if quantity > 1:
        return f"{base_name} {quantity}"
    return base_name


async def populate_shopping_list(
    client: TrelloClient,
    prefs: Prefs,
) -> None:
    """Populate shopping list from selected recipes.

    Args:
        client: Trello client
        prefs: Preferences
    """
    # Get all cards on the board
    cards = await client.get_board_cards(prefs.board)

    # Find cards with the populate label
    for card in cards:
        has_populate_label = any(
            label.get("name") == prefs.populate_label
            for label in card.labels
        )
        if not has_populate_label:
            continue

        logger.info(f"Populating shopping list from {card.name}")

        # Get cards from the selected recipes list
        selected_recipes = await client.get_list_cards(prefs.selected_list)
        logger.info(f"Found {len(selected_recipes)} selected recipes")

        # Keep track of items and their quantities to merge duplicates
        # Maps lowercase base name -> (original_base_name, total_quantity)
        item_data: dict[str, tuple[str, int]] = {}

        # Get or create a checklist on the populate card
        if not card.idChecklists:
            # Create a new checklist if one doesn't exist
            logger.info(f"Creating new checklist on card {card.name}")
            new_checklist = await client.create_checklist(card.id, "Shopping List")
            target_checklist_id = new_checklist.id
        else:
            # Use the first existing checklist
            target_checklist_id = card.idChecklists[0]

        # For each recipe card in the selected list
        for recipe_card in selected_recipes:
            logger.info(f"Processing recipe: {recipe_card.name}")

            # Get all checklists on the recipe card
            for id_checklist in recipe_card.idChecklists:
                checklist = await client.get_checklist(id_checklist)

                # Copy each item from the recipe checklist to the populate card's checklist
                for checklist_item in checklist.checkItems:
                    # Skip checked items (treated as optional/not needed)
                    if checklist_item.state == "complete":
                        logger.debug(f"Skipping checked item: {checklist_item.name}")
                        continue

                    # Parse the item to extract base name and quantity
                    base_name, quantity = parse_item_quantity(checklist_item.name)
                    base_name_lower = base_name.lower()

                    # Merge quantities for duplicate items
                    if base_name_lower in item_data:
                        original_name, existing_quantity = item_data[base_name_lower]
                        item_data[base_name_lower] = (original_name, existing_quantity + quantity)
                        logger.debug(
                            f"Merging duplicate item: {checklist_item.name} "
                            f"(total quantity now: {existing_quantity + quantity})"
                        )
                    else:
                        item_data[base_name_lower] = (base_name, quantity)
                        logger.debug(f"Added item: {checklist_item.name}")

        # Add all items with their merged quantities to the checklist
        for original_name, total_quantity in item_data.values():
            # Preserve the original casing of the first occurrence
            formatted_name = format_item_with_quantity(original_name, total_quantity)
            await client.add_checklist_item(
                target_checklist_id,
                formatted_name
            )
            logger.debug(f"Added merged item: {formatted_name}")

        # Move recipe cards back to the available recipes list
        for recipe_card in selected_recipes:
            # Reset all checkmarks before moving back to available pool
            for id_checklist in recipe_card.idChecklists:
                checklist = await client.get_checklist(id_checklist)
                for checklist_item in checklist.checkItems:
                    if checklist_item.state == "complete":
                        # Reset checked items to incomplete
                        checklist_item.state = "incomplete"
                        await client.update_checklist_item(
                            recipe_card.id,
                            id_checklist,
                            checklist_item.id,
                            checklist_item,
                        )
                        logger.debug(f"Reset checkmark for item: {checklist_item.name}")

            await client.move_card_to_list(recipe_card.id, prefs.available_list)
            logger.info(f"Moved recipe {recipe_card.name} back to available list")

        # Remove the populate label when done
        await reset_label(client, prefs.populate_label, [card.id])
        logger.info(f"Populating {card.name} done")


async def list_board_lists(client: TrelloClient, prefs: Prefs) -> None:
    """Print all lists on a board.

    Args:
        client: Trello client
        prefs: Preferences
    """
    try:
        lists = await client.get_board_lists(prefs.board)
        print("Available lists on your board:")
        print(json.dumps(lists, indent=2))
    except Exception as error:
        logger.error(f"Error fetching board lists: {error}")


def train(checklist: Checklist, old_scores: Scores) -> Scores:
    """Train scores using ELO ranking.

    Args:
        checklist: Checklist to train on
        old_scores: Previous scores

    Returns:
        Updated scores
    """
    logger.info(f"Training on {len(checklist.checkItems)} items")

    # Create new scores dict from old scores
    scores = make_scores(dict(old_scores))

    # Create ELO ranking system
    elo = EloRank()

    # Snapshot starting ratings so every comparison in this round is judged
    # against the same baseline, regardless of the items' iteration order.
    items = checklist.checkItems
    starting_scores = {item.name: lookup(scores, item.name) for item in items}
    deltas: defaultdict[str, float] = defaultdict(float)

    # Process each unordered pair of items exactly once
    for i, current in enumerate(items):
        current_score = starting_scores[current.name]

        for compare in items[i + 1:]:
            # Same object
            if current.pos == compare.pos:
                continue

            # Lower pos means earlier in sequence
            compare_score = starting_scores[compare.name]

            current_expected = elo.get_expected(current_score, compare_score)
            compare_expected = elo.get_expected(compare_score, current_score)

            current_actual = 0 if current.pos < compare.pos else 1
            compare_actual = 1 - current_actual

            deltas[current.name] += elo.update_rating(current_expected, current_actual, 0.0)
            deltas[compare.name] += elo.update_rating(compare_expected, compare_actual, 0.0)

    for item in items:
        update(scores, item.name, starting_scores[item.name] + deltas[item.name])

    return scores


async def main() -> None:
    """Main entry point."""
    # Load preferences
    prefs_path = Path(".trello.json")
    if not prefs_path.exists():
        logger.error("Error: .trello.json not found")
        sys.exit(1)

    prefs_data = json.loads(prefs_path.read_text())
    prefs = Prefs(prefs_data)

    # Create client
    client = create_client(prefs)

    # Check for command line arguments
    if "--list-ids" in sys.argv:
        await list_board_lists(client, prefs)
        return

    # Get training data
    checklists = await get_train_set(client, prefs)

    # Load or initialize scores
    scores_path = Path("scores.json")
    if scores_path.exists():
        scores_data = json.loads(scores_path.read_text())
        scores = make_scores(scores_data)
    else:
        scores = make_scores()

    # Train on all checklists
    for checklist in checklists:
        scores = train(checklist, scores)

    # Save scores
    scores_path.write_text(json.dumps(dict(scores), indent=2))

    # Reset training labels
    await reset_label(
        client,
        prefs.train_label,
        [c.idCard for c in checklists]
    )

    # Order lists
    await order_list(client, scores, prefs)

    # Populate shopping list
    await populate_shopping_list(client, prefs)


if __name__ == "__main__":
    asyncio.run(main())
