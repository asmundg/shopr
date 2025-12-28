"""Trello API client for shopr."""

from typing import Any, Awaitable, Callable, Literal, Protocol
from dataclasses import dataclass


ROOT = "https://api.trello.com"


@dataclass
class Board:
    """Trello board representation."""
    id: str
    desc: str
    descData: str
    closed: bool
    idOrganization: str
    pinned: bool
    url: str
    shortUrl: str
    prefs: dict[str, Any]
    labelNames: dict[str, str]
    limits: dict[str, Any]
    starred: bool
    memberships: str
    shortLink: str
    subscribed: bool
    powerUps: str
    dateLastActivity: str
    dateLastView: str
    idTags: str
    datePluginDisable: str
    creationMethod: str
    ixUpdate: int
    templateGallery: str
    enterpriseOwned: bool


@dataclass
class Card:
    """Trello card representation."""
    id: str
    address: str | None
    badges: dict[str, Any]
    checkItemStates: list[str]
    closed: bool
    coordinates: str | None
    creationMethod: str
    dateLastActivity: str
    desc: str
    descData: dict[str, Any]
    due: str | None
    dueReminder: str | None
    email: str | None
    idBoard: str
    idChecklists: list[str]
    idLabels: list[str]
    idList: str
    idMembers: list[str]
    idMembersVoted: list[str]
    idShort: int
    labels: list[dict[str, Any]]
    limits: dict[str, Any]
    locationName: str | None
    manualCoverAttachment: bool
    name: str
    pos: int
    shortLink: str
    shortUrl: str
    subscribed: bool
    url: str
    cover: dict[str, Any]


@dataclass
class ChecklistItem:
    """Trello checklist item representation."""
    idChecklist: str
    state: str
    idMember: str | None
    id: str
    name: str
    nameData: Any | None
    pos: int
    due: str | None


@dataclass
class Checklist:
    """Trello checklist representation."""
    id: str
    name: str
    idCard: str
    pos: int
    idBoard: str
    checkItems: list[ChecklistItem]


class RequestFactory(Protocol):
    """Protocol for HTTP request factory."""
    async def __call__(
        self,
        method: Literal["get", "delete", "post", "put"],
        url: str,
        params: dict[str, Any],
        data: Any = None,
    ) -> dict[str, Any]:
        """Make an HTTP request."""
        ...


class TrelloClient:
    """Client for interacting with the Trello API."""

    def __init__(
        self,
        key: str,
        token: str,
        make_request: RequestFactory,
    ):
        """Initialize the Trello client.

        Args:
            key: Trello API key
            token: Trello API token
            make_request: Function to make HTTP requests
        """
        self.key = key
        self.token = token
        self.make_request = make_request

    async def get_board(self, id: str) -> Board:
        """Get a board by ID."""
        result = await self.make_request(
            "get",
            f"{ROOT}/1/boards/{id}",
            {"key": self.key, "token": self.token}
        )
        return Board(**result)

    async def get_board_checklists(self, id: str) -> list[Checklist]:
        """Get all checklists on a board."""
        result = await self.make_request(
            "get",
            f"{ROOT}/1/boards/{id}/checklists",
            {"key": self.key, "token": self.token, "fields": "all"}
        )
        return [Checklist(**item) for item in result]

    async def get_board_cards(self, id: str) -> list[Card]:
        """Get all cards on a board."""
        result = await self.make_request(
            "get",
            f"{ROOT}/1/boards/{id}/cards",
            {"key": self.key, "token": self.token}
        )
        return [Card(**item) for item in result]

    async def get_card(self, id: str) -> Card:
        """Get a card by ID."""
        result = await self.make_request(
            "get",
            f"{ROOT}/1/cards/{id}",
            {"key": self.key, "token": self.token}
        )
        return Card(**result)

    async def get_checklist(self, id: str) -> Checklist:
        """Get a checklist by ID."""
        result = await self.make_request(
            "get",
            f"{ROOT}/1/checklists/{id}",
            {"key": self.key, "token": self.token}
        )
        # Convert checkItems to ChecklistItem objects
        check_items = [ChecklistItem(**item) for item in result.get("checkItems", [])]
        result["checkItems"] = check_items
        return Checklist(**result)

    async def update_checklist(self, id: str, data: Checklist) -> dict[str, Any]:
        """Update a checklist."""
        return await self.make_request(
            "put",
            f"{ROOT}/1/checklists/{id}",
            {"key": self.key, "token": self.token},
            data
        )

    async def update_checklist_item(
        self,
        id_card: str,
        id_checklist: str,
        id_check_item: str,
        data: ChecklistItem,
    ) -> dict[str, Any]:
        """Update a checklist item."""
        return await self.make_request(
            "put",
            f"{ROOT}/1/cards/{id_card}/checklist/{id_checklist}/checkItem/{id_check_item}",
            {"key": self.key, "token": self.token},
            {
                "name": data.name,
                "pos": data.pos,
                "state": data.state,
            }
        )

    async def add_checklist_item(
        self,
        id_checklist: str,
        name: str,
        pos: int | None = None,
    ) -> ChecklistItem:
        """Add a checklist item to a checklist."""
        data = {"name": name}
        if pos is not None:
            data["pos"] = pos

        result = await self.make_request(
            "post",
            f"{ROOT}/1/checklists/{id_checklist}/checkItems",
            {"key": self.key, "token": self.token},
            data
        )
        return ChecklistItem(**result)

    async def get_list_cards(self, id_list: str) -> list[Card]:
        """Get cards in a specific list."""
        result = await self.make_request(
            "get",
            f"{ROOT}/1/lists/{id_list}/cards",
            {"key": self.key, "token": self.token}
        )
        return [Card(**item) for item in result]

    async def move_card_to_list(self, id_card: str, id_list: str) -> dict[str, Any]:
        """Move a card to a different list."""
        return await self.make_request(
            "put",
            f"{ROOT}/1/cards/{id_card}",
            {"key": self.key, "token": self.token},
            {"idList": id_list}
        )

    async def remove_label(self, id_card: str, id_label: str) -> dict[str, Any]:
        """Remove a label from a card."""
        return await self.make_request(
            "delete",
            f"{ROOT}/1/cards/{id_card}/idLabels/{id_label}",
            {"key": self.key, "token": self.token}
        )

    async def get_board_lists(self, id_board: str) -> list[dict[str, Any]]:
        """Get all lists on a board."""
        return await self.make_request(
            "get",
            f"{ROOT}/1/boards/{id_board}/lists",
            {"key": self.key, "token": self.token}
        )

    async def create_checklist(
        self,
        id_card: str,
        name: str = "Checklist",
    ) -> Checklist:
        """Create a new checklist on a card."""
        result = await self.make_request(
            "post",
            f"{ROOT}/1/cards/{id_card}/checklists",
            {"key": self.key, "token": self.token},
            {"name": name}
        )
        return Checklist(**result)


def create_trello_client(
    key: str,
    token: str,
    make_request: RequestFactory,
) -> TrelloClient:
    """Create a Trello client.

    Args:
        key: Trello API key
        token: Trello API token
        make_request: Function to make HTTP requests

    Returns:
        TrelloClient instance
    """
    return TrelloClient(key, token, make_request)
