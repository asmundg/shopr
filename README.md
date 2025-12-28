# shopr

Trello-based shopping list sorter

## Requirements

- Python 3.13 or later

## Installation

```bash
pip install -r requirements.txt
```

Or using pip directly:

```bash
pip install httpx elote
```

## Configuration

Create a `.trello.json` file with your Trello API credentials:

```json
{
  "token": "your-trello-token",
  "key": "your-trello-api-key",
  "board": "your-board-id",
  "trainLabel": "train",
  "orderLabel": "order",
  "populateLabel": "populate",
  "availableList": "available-recipes-list-id",
  "selectedList": "selected-recipes-list-id"
}
```

## Usage

Run the shopr application:

```bash
python shopr.py
```

List all lists on your board (to get list IDs):

```bash
python shopr.py --list-ids
```

## Features

- **Training**: Uses ELO ranking to learn item preferences based on checklist ordering
- **Ordering**: Automatically sorts shopping list items based on learned preferences
- **Recipe Management**: Populate shopping lists from selected recipe cards

## How it Works

1. Mark cards with the `train` label to teach shopr about your preferred shopping order
2. Mark cards with the `order` label to automatically sort their checklists
3. Add recipe cards to the selected list and mark a card with the `populate` label to create a shopping list from recipes

The application learns from your manual ordering and applies that knowledge to automatically sort future lists.
