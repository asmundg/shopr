"""Tests for the main shopr business logic."""

import json

import pytest
from pytest_httpx import HTTPXMock

from shopr.main import (
    DEFAULT_SCORE,
    make_scores,
    lookup_candidates,
    lookup,
    update,
    train,
    get_train_set,
    order_list,
    populate_shopping_list,
    parse_item_quantity,
    format_item_with_quantity,
    Prefs,
)
from shopr.trello import (
    Card,
    Checklist,
    ChecklistItem,
    TrelloClient,
    ROOT,
)


class TestMakeScores:
    """Tests for make_scores function."""

    def test_empty_scores_returns_default(self) -> None:
        """Test getting a missing key returns default score."""
        scores = make_scores()
        assert scores["missing"] == DEFAULT_SCORE

    def test_initialized_with_data(self) -> None:
        """Test initializing with existing data."""
        scores = make_scores({"milk": 500.0})
        assert scores["milk"] == 500.0

    def test_missing_key_returns_default(self) -> None:
        """Test that missing keys return default score."""
        scores = make_scores({"milk": 500.0})
        assert scores["bread"] == DEFAULT_SCORE


class TestParseItemQuantity:
    """Tests for parse_item_quantity function."""

    def test_item_without_quantity(self) -> None:
        """Test parsing item without quantity defaults to 1."""
        assert parse_item_quantity("eggs") == ("eggs", 1)

    def test_item_with_quantity(self) -> None:
        """Test parsing item with quantity."""
        assert parse_item_quantity("eggs 2") == ("eggs", 2)

    def test_item_with_larger_quantity(self) -> None:
        """Test parsing item with larger quantity."""
        assert parse_item_quantity("milk 10") == ("milk", 10)

    def test_multi_word_item_with_quantity(self) -> None:
        """Test parsing multi-word item with quantity."""
        assert parse_item_quantity("whole milk 3") == ("whole milk", 3)

    def test_item_with_non_numeric_suffix(self) -> None:
        """Test that non-numeric suffix is kept in name."""
        assert parse_item_quantity("eggs large") == ("eggs large", 1)

    def test_strips_whitespace(self) -> None:
        """Test that whitespace is stripped."""
        assert parse_item_quantity("  eggs  ") == ("eggs", 1)
        assert parse_item_quantity("  eggs 2  ") == ("eggs", 2)


class TestFormatItemWithQuantity:
    """Tests for format_item_with_quantity function."""

    def test_quantity_one_no_suffix(self) -> None:
        """Test that quantity 1 doesn't add suffix."""
        assert format_item_with_quantity("eggs", 1) == "eggs"

    def test_quantity_greater_than_one_adds_suffix(self) -> None:
        """Test that quantity > 1 adds suffix."""
        assert format_item_with_quantity("eggs", 2) == "eggs 2"
        assert format_item_with_quantity("eggs", 3) == "eggs 3"
        assert format_item_with_quantity("milk", 10) == "milk 10"


class TestLookupCandidates:
    """Tests for lookup_candidates function."""

    def test_simple_name(self) -> None:
        """Test simple single-word name."""
        assert lookup_candidates("Milk") == ["milk"]

    def test_multi_word(self) -> None:
        """Test multi-word name returns sorted words."""
        assert lookup_candidates("Whole Milk") == ["milk", "whole"]

    def test_strips_unsorted_tag(self) -> None:
        """Test that [unsorted] tag is removed."""
        assert lookup_candidates("Milk [unsorted]") == ["milk"]

    def test_strips_numbers_and_parens(self) -> None:
        """Test that numbers and parentheses are removed."""
        assert lookup_candidates("Milk (2L)") == ["l", "milk"]

    def test_normalizes_whitespace(self) -> None:
        """Test that extra whitespace is normalized."""
        assert lookup_candidates("  Whole   Milk  ") == ["milk", "whole"]


class TestLookup:
    """Tests for lookup function."""

    def test_no_score_returns_default(self) -> None:
        """Test that missing items return default score."""
        scores = make_scores()
        assert lookup(scores, "Unknown Item") == DEFAULT_SCORE

    def test_exact_match(self) -> None:
        """Test exact match on full key."""
        scores = make_scores({"milk,whole": 500.0})
        assert lookup(scores, "Whole Milk") == 500.0

    def test_partial_match_uses_longest(self) -> None:
        """Test that partial matches use longest candidate."""
        scores = make_scores({"milk": 600.0})
        assert lookup(scores, "Whole Milk") == 600.0

    def test_full_key_preferred_over_partial(self) -> None:
        """Test that full key is preferred over partial match."""
        scores = make_scores({"milk,whole": 500.0, "milk": 600.0})
        # Full key "milk,whole" should be preferred (it's longer)
        assert lookup(scores, "Whole Milk") == 500.0


class TestUpdate:
    """Tests for update function."""

    def test_updates_all_candidates(self) -> None:
        """Test that update sets score for all candidates."""
        scores = make_scores()
        update(scores, "Whole Milk", 500.0)

        assert scores["milk,whole"] == 500.0
        assert scores["milk"] == 500.0
        assert scores["whole"] == 500.0


class TestTrain:
    """Tests for train function."""

    def test_train_updates_scores_based_on_position(self) -> None:
        """Test that training updates scores based on item positions."""
        checklist = Checklist(
            id="checklist1",
            name="Shopping",
            checkItems=[
                ChecklistItem(
                    id="item1",
                    idChecklist="checklist1",
                    name="Milk",
                    pos=1000,  # First in store
                ),
                ChecklistItem(
                    id="item2",
                    idChecklist="checklist1",
                    name="Bread",
                    pos=2000,  # Second in store
                ),
            ],
        )
        old_scores = make_scores()

        new_scores = train(checklist, old_scores)

        # Milk (pos=1000) should have lower score than Bread (pos=2000)
        # Lower score = earlier in the store
        milk_score = new_scores["milk"]
        bread_score = new_scores["bread"]
        assert milk_score < bread_score

    def test_train_preserves_relative_ordering(self) -> None:
        """Test that multiple items maintain relative ordering after training."""
        checklist = Checklist(
            id="checklist1",
            name="Shopping",
            checkItems=[
                ChecklistItem(id="1", idChecklist="c", name="First", pos=100),
                ChecklistItem(id="2", idChecklist="c", name="Second", pos=200),
                ChecklistItem(id="3", idChecklist="c", name="Third", pos=300),
            ],
        )

        new_scores = train(checklist, make_scores())

        first = new_scores["first"]
        second = new_scores["second"]
        third = new_scores["third"]

        assert first < second < third

    def test_train_does_not_mutate_old_scores(self) -> None:
        """Test that training returns new Scores, not mutating old."""
        old_scores = make_scores({"milk": 500.0})
        checklist = Checklist(
            id="c1",
            name="Test",
            checkItems=[
                ChecklistItem(id="1", idChecklist="c1", name="Milk", pos=100),
                ChecklistItem(id="2", idChecklist="c1", name="Bread", pos=200),
            ],
        )

        new_scores = train(checklist, old_scores)

        # Old scores should be unchanged
        assert old_scores["milk"] == 500.0
        assert "bread" not in old_scores
        # New scores should have bread
        assert "bread" in new_scores


@pytest.fixture
def prefs() -> Prefs:
    """Create test preferences."""
    return Prefs({
        "key": "test_key",
        "token": "test_token",
        "board": "board123",
        "trainLabel": "train",
        "orderLabel": "order",
        "populateLabel": "populate",
        "availableList": "available123",
        "selectedList": "selected123",
    })


@pytest.fixture
def trello_client() -> TrelloClient:
    """Create a TrelloClient for testing."""
    return TrelloClient(key="test_key", token="test_token")


class TestGetTrainSet:
    """Tests for get_train_set function."""

    async def test_returns_checklists_from_cards_with_train_label(
        self,
        trello_client: TrelloClient,
        prefs: Prefs,
        httpx_mock: HTTPXMock,
    ) -> None:
        """Test that only checklists from cards with train label are returned."""
        card_with_label = Card(
            id="card1",
            idBoard="board123",
            name="Card with train label",
            idChecklists=["checklist1"],
            labels=[{"id": "l1", "name": "train"}],
        )
        card_without_label = Card(
            id="card2",
            idBoard="board123",
            name="Card without train label",
            idChecklists=["checklist2"],
            labels=[],
        )
        checklist = Checklist(
            id="checklist1",
            name="Shopping",
            checkItems=[
                ChecklistItem(id="item1", idChecklist="checklist1", name="Milk", pos=1000),
            ],
        )

        httpx_mock.add_response(
            url=f"{ROOT}/1/boards/board123/cards?key=test_key&token=test_token",
            json=[card_with_label.model_dump(), card_without_label.model_dump()],
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/checklist1?key=test_key&token=test_token",
            json=checklist.model_dump(),
        )

        result = await get_train_set(trello_client, prefs)

        assert len(result) == 1
        assert result[0].id == "checklist1"

    async def test_returns_empty_when_no_train_labels(
        self,
        trello_client: TrelloClient,
        prefs: Prefs,
        httpx_mock: HTTPXMock,
    ) -> None:
        """Test that empty list is returned when no cards have train label."""
        card = Card(
            id="card1",
            idBoard="board123",
            name="Card without label",
            idChecklists=["checklist1"],
            labels=[],
        )

        httpx_mock.add_response(
            url=f"{ROOT}/1/boards/board123/cards?key=test_key&token=test_token",
            json=[card.model_dump()],
        )

        result = await get_train_set(trello_client, prefs)

        assert result == []


class TestOrderList:
    """Tests for order_list function."""

    async def test_updates_item_positions_based_on_scores(
        self,
        trello_client: TrelloClient,
        prefs: Prefs,
        httpx_mock: HTTPXMock,
    ) -> None:
        """Test that items are reordered based on their scores."""
        scores = make_scores({"bread": 200.0, "milk": 100.0})

        card = Card(
            id="card1",
            idBoard="board123",
            name="Shopping List",
            idChecklists=["checklist1"],
            labels=[{"id": "l1", "name": "order"}],
        )
        checklist = Checklist(
            id="checklist1",
            name="Items",
            checkItems=[
                ChecklistItem(id="item1", idChecklist="checklist1", name="Bread", pos=1000),
                ChecklistItem(id="item2", idChecklist="checklist1", name="Milk", pos=2000),
            ],
        )

        httpx_mock.add_response(
            url=f"{ROOT}/1/boards/board123/cards?key=test_key&token=test_token",
            json=[card.model_dump()],
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/checklist1?key=test_key&token=test_token",
            json=checklist.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/card1/checklist/checklist1/checkItem/item1?key=test_key&token=test_token",
            method="PUT",
            json={"id": "item1"},
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/card1/checklist/checklist1/checkItem/item2?key=test_key&token=test_token",
            method="PUT",
            json={"id": "item2"},
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/card1?key=test_key&token=test_token",
            json=card.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/card1/idLabels/l1?key=test_key&token=test_token",
            method="DELETE",
            json={},
        )

        await order_list(trello_client, scores, prefs)

        # Verify the update calls were made
        requests = httpx_mock.get_requests()
        put_requests = [r for r in requests if r.method == "PUT"]
        assert len(put_requests) == 2

    async def test_adds_unsorted_tag_to_unknown_items(
        self,
        trello_client: TrelloClient,
        prefs: Prefs,
        httpx_mock: HTTPXMock,
    ) -> None:
        """Test that items without scores get [unsorted] tag added."""
        scores = make_scores()  # Empty scores

        card = Card(
            id="card1",
            idBoard="board123",
            name="Shopping List",
            idChecklists=["checklist1"],
            labels=[{"id": "l1", "name": "order"}],
        )
        checklist = Checklist(
            id="checklist1",
            name="Items",
            checkItems=[
                ChecklistItem(id="item1", idChecklist="checklist1", name="Unknown Item", pos=1000),
            ],
        )

        httpx_mock.add_response(
            url=f"{ROOT}/1/boards/board123/cards?key=test_key&token=test_token",
            json=[card.model_dump()],
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/checklist1?key=test_key&token=test_token",
            json=checklist.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/card1/checklist/checklist1/checkItem/item1?key=test_key&token=test_token",
            method="PUT",
            json={"id": "item1"},
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/card1?key=test_key&token=test_token",
            json=card.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/card1/idLabels/l1?key=test_key&token=test_token",
            method="DELETE",
            json={},
        )

        await order_list(trello_client, scores, prefs)

        # Check that the PUT request included the [unsorted] tag
        requests = httpx_mock.get_requests()
        put_requests = [r for r in requests if r.method == "PUT"]
        assert len(put_requests) == 1

        body = json.loads(put_requests[0].content)
        assert "[unsorted]" in body["name"]


class TestPopulateShoppingList:
    """Tests for populate_shopping_list function."""

    async def test_populates_from_selected_recipes(
        self,
        trello_client: TrelloClient,
        prefs: Prefs,
        httpx_mock: HTTPXMock,
    ) -> None:
        """Test that items from selected recipes are added to shopping list."""
        populate_card = Card(
            id="populate_card",
            idBoard="board123",
            name="Shopping List",
            idChecklists=["target_checklist"],
            labels=[{"id": "l1", "name": "populate"}],
        )
        recipe_card = Card(
            id="recipe1",
            idBoard="board123",
            name="Pasta Recipe",
            idChecklists=["recipe_checklist"],
            labels=[],
        )
        recipe_checklist = Checklist(
            id="recipe_checklist",
            name="Ingredients",
            checkItems=[
                ChecklistItem(id="i1", idChecklist="recipe_checklist", name="Pasta", pos=1),
                ChecklistItem(id="i2", idChecklist="recipe_checklist", name="Tomatoes", pos=2),
            ],
        )
        new_item1 = ChecklistItem(id="new_item1", idChecklist="target_checklist", name="Pasta", pos=1)
        new_item2 = ChecklistItem(id="new_item2", idChecklist="target_checklist", name="Tomatoes", pos=2)

        httpx_mock.add_response(
            url=f"{ROOT}/1/boards/board123/cards?key=test_key&token=test_token",
            json=[populate_card.model_dump()],
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/lists/selected123/cards?key=test_key&token=test_token",
            json=[recipe_card.model_dump()],
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/recipe_checklist?key=test_key&token=test_token",
            json=recipe_checklist.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/target_checklist/checkItems?key=test_key&token=test_token",
            method="POST",
            json=new_item1.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/target_checklist/checkItems?key=test_key&token=test_token",
            method="POST",
            json=new_item2.model_dump(),
        )
        # Mock getting checklist again for resetting checkmarks
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/recipe_checklist?key=test_key&token=test_token",
            json=recipe_checklist.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/recipe1?key=test_key&token=test_token",
            method="PUT",
            json={"id": "recipe1"},
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/populate_card?key=test_key&token=test_token",
            json=populate_card.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/populate_card/idLabels/l1?key=test_key&token=test_token",
            method="DELETE",
            json={},
        )

        await populate_shopping_list(trello_client, prefs)

        requests = httpx_mock.get_requests()
        post_requests = [r for r in requests if r.method == "POST"]
        assert len(post_requests) == 2

        posted_names = [json.loads(r.content)["name"] for r in post_requests]
        assert "Pasta" in posted_names
        assert "Tomatoes" in posted_names

    async def test_merges_duplicate_items(
        self,
        trello_client: TrelloClient,
        prefs: Prefs,
        httpx_mock: HTTPXMock,
    ) -> None:
        """Test that duplicate items are merged with quantities."""
        populate_card = Card(
            id="populate_card",
            idBoard="board123",
            name="Shopping List",
            idChecklists=["target_checklist"],
            labels=[{"id": "l1", "name": "populate"}],
        )
        recipe1 = Card(
            id="recipe1",
            idBoard="board123",
            name="Recipe 1",
            idChecklists=["checklist1"],
            labels=[],
        )
        recipe2 = Card(
            id="recipe2",
            idBoard="board123",
            name="Recipe 2",
            idChecklists=["checklist2"],
            labels=[],
        )
        checklist1 = Checklist(
            id="checklist1",
            name="Ingredients",
            checkItems=[
                ChecklistItem(id="i1", idChecklist="checklist1", name="Milk", pos=1),
            ],
        )
        checklist2 = Checklist(
            id="checklist2",
            name="Ingredients",
            checkItems=[
                ChecklistItem(id="i2", idChecklist="checklist2", name="milk", pos=1),  # lowercase duplicate
            ],
        )
        new_item = ChecklistItem(id="new_item", idChecklist="target_checklist", name="milk 2", pos=1)

        httpx_mock.add_response(
            url=f"{ROOT}/1/boards/board123/cards?key=test_key&token=test_token",
            json=[populate_card.model_dump()],
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/lists/selected123/cards?key=test_key&token=test_token",
            json=[recipe1.model_dump(), recipe2.model_dump()],
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/checklist1?key=test_key&token=test_token",
            json=checklist1.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/checklist2?key=test_key&token=test_token",
            json=checklist2.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/target_checklist/checkItems?key=test_key&token=test_token",
            method="POST",
            json=new_item.model_dump(),
        )
        # Mock getting checklists again for resetting checkmarks
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/checklist1?key=test_key&token=test_token",
            json=checklist1.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/checklist2?key=test_key&token=test_token",
            json=checklist2.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/recipe1?key=test_key&token=test_token",
            method="PUT",
            json={"id": "recipe1"},
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/recipe2?key=test_key&token=test_token",
            method="PUT",
            json={"id": "recipe2"},
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/populate_card?key=test_key&token=test_token",
            json=populate_card.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/populate_card/idLabels/l1?key=test_key&token=test_token",
            method="DELETE",
            json={},
        )

        await populate_shopping_list(trello_client, prefs)

        # Only one item should have been added with merged quantity
        # The casing should match the first occurrence ("Milk")
        requests = httpx_mock.get_requests()
        post_requests = [r for r in requests if r.method == "POST"]
        assert len(post_requests) == 1
        posted_name = json.loads(post_requests[0].content)["name"]
        assert posted_name == "Milk 2"

    async def test_merges_items_with_explicit_quantities(
        self,
        trello_client: TrelloClient,
        prefs: Prefs,
        httpx_mock: HTTPXMock,
    ) -> None:
        """Test that items with explicit quantities are merged correctly (e.g., 'eggs' + 'eggs 2' = 'eggs 3')."""
        populate_card = Card(
            id="populate_card",
            idBoard="board123",
            name="Shopping List",
            idChecklists=["target_checklist"],
            labels=[{"id": "l1", "name": "populate"}],
        )
        recipe1 = Card(
            id="recipe1",
            idBoard="board123",
            name="Recipe 1",
            idChecklists=["checklist1"],
            labels=[],
        )
        recipe2 = Card(
            id="recipe2",
            idBoard="board123",
            name="Recipe 2",
            idChecklists=["checklist2"],
            labels=[],
        )
        checklist1 = Checklist(
            id="checklist1",
            name="Ingredients",
            checkItems=[
                ChecklistItem(id="i1", idChecklist="checklist1", name="eggs", pos=1),
            ],
        )
        checklist2 = Checklist(
            id="checklist2",
            name="Ingredients",
            checkItems=[
                ChecklistItem(id="i2", idChecklist="checklist2", name="eggs 2", pos=1),
            ],
        )
        new_item = ChecklistItem(id="new_item", idChecklist="target_checklist", name="eggs 3", pos=1)

        httpx_mock.add_response(
            url=f"{ROOT}/1/boards/board123/cards?key=test_key&token=test_token",
            json=[populate_card.model_dump()],
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/lists/selected123/cards?key=test_key&token=test_token",
            json=[recipe1.model_dump(), recipe2.model_dump()],
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/checklist1?key=test_key&token=test_token",
            json=checklist1.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/checklist2?key=test_key&token=test_token",
            json=checklist2.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/target_checklist/checkItems?key=test_key&token=test_token",
            method="POST",
            json=new_item.model_dump(),
        )
        # Mock getting checklists again for resetting checkmarks
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/checklist1?key=test_key&token=test_token",
            json=checklist1.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/checklist2?key=test_key&token=test_token",
            json=checklist2.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/recipe1?key=test_key&token=test_token",
            method="PUT",
            json={"id": "recipe1"},
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/recipe2?key=test_key&token=test_token",
            method="PUT",
            json={"id": "recipe2"},
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/populate_card?key=test_key&token=test_token",
            json=populate_card.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/populate_card/idLabels/l1?key=test_key&token=test_token",
            method="DELETE",
            json={},
        )

        await populate_shopping_list(trello_client, prefs)

        # Only one item should have been added with merged quantity (1 + 2 = 3)
        requests = httpx_mock.get_requests()
        post_requests = [r for r in requests if r.method == "POST"]
        assert len(post_requests) == 1
        posted_name = json.loads(post_requests[0].content)["name"]
        assert posted_name == "eggs 3"

    async def test_creates_checklist_if_none_exists(
        self,
        trello_client: TrelloClient,
        prefs: Prefs,
        httpx_mock: HTTPXMock,
    ) -> None:
        """Test that a new checklist is created if card has none."""
        populate_card = Card(
            id="populate_card",
            idBoard="board123",
            name="Shopping List",
            idChecklists=[],  # No checklists
            labels=[{"id": "l1", "name": "populate"}],
        )
        new_checklist = Checklist(id="new_checklist", name="Shopping List", checkItems=[])

        httpx_mock.add_response(
            url=f"{ROOT}/1/boards/board123/cards?key=test_key&token=test_token",
            json=[populate_card.model_dump()],
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/lists/selected123/cards?key=test_key&token=test_token",
            json=[],  # No recipes
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/populate_card/checklists?key=test_key&token=test_token",
            method="POST",
            json=new_checklist.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/populate_card?key=test_key&token=test_token",
            json=populate_card.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/populate_card/idLabels/l1?key=test_key&token=test_token",
            method="DELETE",
            json={},
        )

        await populate_shopping_list(trello_client, prefs)

        requests = httpx_mock.get_requests()
        post_requests = [r for r in requests if r.method == "POST"]
        assert len(post_requests) == 1

        body = json.loads(post_requests[0].content)
        assert body["name"] == "Shopping List"

    async def test_skips_checked_items_and_resets_checkmarks(
        self,
        trello_client: TrelloClient,
        prefs: Prefs,
        httpx_mock: HTTPXMock,
    ) -> None:
        """Test that checked items are skipped and checkmarks are reset when moving cards back."""
        populate_card = Card(
            id="populate_card",
            idBoard="board123",
            name="Shopping List",
            idChecklists=["target_checklist"],
            labels=[{"id": "l1", "name": "populate"}],
        )
        recipe_card = Card(
            id="recipe1",
            idBoard="board123",
            name="Recipe",
            idChecklists=["recipe_checklist"],
            labels=[],
        )
        recipe_checklist = Checklist(
            id="recipe_checklist",
            name="Ingredients",
            checkItems=[
                ChecklistItem(id="i1", idChecklist="recipe_checklist", name="Pasta", pos=1, state="incomplete"),
                ChecklistItem(id="i2", idChecklist="recipe_checklist", name="Tomatoes", pos=2, state="complete"),  # Checked
                ChecklistItem(id="i3", idChecklist="recipe_checklist", name="Cheese", pos=3, state="incomplete"),
                ChecklistItem(id="i4", idChecklist="recipe_checklist", name="Garlic", pos=4, state="complete"),  # Checked
            ],
        )
        new_item1 = ChecklistItem(id="new_item1", idChecklist="target_checklist", name="Pasta", pos=1)
        new_item2 = ChecklistItem(id="new_item2", idChecklist="target_checklist", name="Cheese", pos=2)

        # Mock getting board cards
        httpx_mock.add_response(
            url=f"{ROOT}/1/boards/board123/cards?key=test_key&token=test_token",
            json=[populate_card.model_dump()],
        )
        # Mock getting selected recipes
        httpx_mock.add_response(
            url=f"{ROOT}/1/lists/selected123/cards?key=test_key&token=test_token",
            json=[recipe_card.model_dump()],
        )
        # Mock getting recipe checklist (first time for gathering items)
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/recipe_checklist?key=test_key&token=test_token",
            json=recipe_checklist.model_dump(),
        )
        # Mock adding unchecked items to target checklist
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/target_checklist/checkItems?key=test_key&token=test_token",
            method="POST",
            json=new_item1.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/target_checklist/checkItems?key=test_key&token=test_token",
            method="POST",
            json=new_item2.model_dump(),
        )
        # Mock getting recipe checklist again (for resetting checkmarks)
        httpx_mock.add_response(
            url=f"{ROOT}/1/checklists/recipe_checklist?key=test_key&token=test_token",
            json=recipe_checklist.model_dump(),
        )
        # Mock updating checked items to reset them
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/recipe1/checklist/recipe_checklist/checkItem/i2?key=test_key&token=test_token",
            method="PUT",
            json={},
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/recipe1/checklist/recipe_checklist/checkItem/i4?key=test_key&token=test_token",
            method="PUT",
            json={},
        )
        # Mock moving card back to available list
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/recipe1?key=test_key&token=test_token",
            method="PUT",
            json={"id": "recipe1"},
        )
        # Mock getting card and removing label
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/populate_card?key=test_key&token=test_token",
            json=populate_card.model_dump(),
        )
        httpx_mock.add_response(
            url=f"{ROOT}/1/cards/populate_card/idLabels/l1?key=test_key&token=test_token",
            method="DELETE",
            json={},
        )

        await populate_shopping_list(trello_client, prefs)

        # Verify only unchecked items were added (Pasta and Cheese, not Tomatoes or Garlic)
        requests = httpx_mock.get_requests()
        post_requests = [r for r in requests if r.method == "POST" and "checkItems" in str(r.url)]
        assert len(post_requests) == 2
        posted_names = [json.loads(r.content)["name"] for r in post_requests]
        assert "Pasta" in posted_names
        assert "Cheese" in posted_names
        assert "Tomatoes" not in posted_names
        assert "Garlic" not in posted_names

        # Verify checked items were reset
        put_requests = [r for r in requests if r.method == "PUT" and "checkItem" in str(r.url)]
        assert len(put_requests) == 2
        # Verify the state was set to incomplete
        for r in put_requests:
            body = json.loads(r.content)
            assert body["state"] == "incomplete"

    async def test_does_nothing_without_populate_label(
        self,
        trello_client: TrelloClient,
        prefs: Prefs,
        httpx_mock: HTTPXMock,
    ) -> None:
        """Test that cards without populate label are ignored."""
        card = Card(
            id="card1",
            idBoard="board123",
            name="Some Card",
            idChecklists=[],
            labels=[{"id": "l1", "name": "other_label"}],
        )

        httpx_mock.add_response(
            url=f"{ROOT}/1/boards/board123/cards?key=test_key&token=test_token",
            json=[card.model_dump()],
        )

        await populate_shopping_list(trello_client, prefs)

        # Only the board cards request should have been made
        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        assert "boards/board123/cards" in str(requests[0].url)
