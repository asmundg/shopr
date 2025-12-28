"""Trello API client for shopr."""

import logging
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict


logger = logging.getLogger("shopr:trello")

ROOT = "https://api.trello.com"


class Card(BaseModel):
    """Trello card representation.

    Only includes fields actually used by the application.
    Unknown fields from the API are ignored.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    idChecklists: list[str] = []
    labels: list[dict[str, Any]] = []


class ChecklistItem(BaseModel):
    """Trello checklist item representation.

    Only includes fields actually used by the application.
    Unknown fields from the API are ignored.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    idChecklist: str
    name: str
    pos: int | float = 0
    state: str = "incomplete"


class Checklist(BaseModel):
    """Trello checklist representation.

    Only includes fields actually used by the application.
    Unknown fields from the API are ignored.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    idCard: str = ""
    checkItems: list[ChecklistItem] = []


class TrelloClient:
    """Client for interacting with the Trello API."""

    def __init__(self, key: str, token: str):
        """Initialize the Trello client.

        Args:
            key: Trello API key
            token: Trello API token
        """
        self.key = key
        self.token = token

    async def _request(
        self,
        method: str,
        url: str,
        params: dict[str, Any] | None = None,
        data: Any = None,
    ) -> Any:
        """Make an HTTP request."""
        all_params = {"key": self.key, "token": self.token, **(params or {})}
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                params=all_params,
                json=data,
            )
            response.raise_for_status()
            return response.json()

    async def get_board_checklists(self, id: str) -> list[Checklist]:
        """Get all checklists on a board."""
        result = await self._request(
            "get", f"{ROOT}/1/boards/{id}/checklists", {"fields": "all"}
        )
        return [Checklist.model_validate(item) for item in result]

    async def get_board_cards(self, id: str) -> list[Card]:
        """Get all cards on a board."""
        result = await self._request("get", f"{ROOT}/1/boards/{id}/cards")
        return [Card.model_validate(item) for item in result]

    async def get_card(self, id: str) -> Card:
        """Get a card by ID."""
        result = await self._request("get", f"{ROOT}/1/cards/{id}")
        return Card.model_validate(result)

    async def get_checklist(self, id: str) -> Checklist:
        """Get a checklist by ID."""
        result = await self._request("get", f"{ROOT}/1/checklists/{id}")
        return Checklist.model_validate(result)

    async def update_checklist(self, id: str, data: Checklist) -> dict[str, Any]:
        """Update a checklist."""
        return await self._request(
            "put", f"{ROOT}/1/checklists/{id}", data=data.model_dump()
        )

    async def update_checklist_item(
        self,
        id_card: str,
        id_checklist: str,
        id_check_item: str,
        data: ChecklistItem,
    ) -> dict[str, Any]:
        """Update a checklist item."""
        return await self._request(
            "put",
            f"{ROOT}/1/cards/{id_card}/checklist/{id_checklist}/checkItem/{id_check_item}",
            data={"name": data.name, "pos": data.pos, "state": data.state},
        )

    async def add_checklist_item(
        self,
        id_checklist: str,
        name: str,
        pos: int | None = None,
    ) -> ChecklistItem:
        """Add a checklist item to a checklist."""
        data: dict[str, Any] = {"name": name}
        if pos is not None:
            data["pos"] = pos
        result = await self._request(
            "post", f"{ROOT}/1/checklists/{id_checklist}/checkItems", data=data
        )
        return ChecklistItem.model_validate(result)

    async def get_list_cards(self, id_list: str) -> list[Card]:
        """Get cards in a specific list."""
        result = await self._request("get", f"{ROOT}/1/lists/{id_list}/cards")
        return [Card.model_validate(item) for item in result]

    async def move_card_to_list(self, id_card: str, id_list: str) -> dict[str, Any]:
        """Move a card to a different list."""
        return await self._request(
            "put", f"{ROOT}/1/cards/{id_card}", data={"idList": id_list}
        )

    async def remove_label(self, id_card: str, id_label: str) -> dict[str, Any]:
        """Remove a label from a card."""
        return await self._request(
            "delete", f"{ROOT}/1/cards/{id_card}/idLabels/{id_label}"
        )

    async def get_board_lists(self, id_board: str) -> list[dict[str, Any]]:
        """Get all lists on a board."""
        return await self._request("get", f"{ROOT}/1/boards/{id_board}/lists")

    async def create_checklist(
        self,
        id_card: str,
        name: str = "Checklist",
    ) -> Checklist:
        """Create a new checklist on a card."""
        result = await self._request(
            "post", f"{ROOT}/1/cards/{id_card}/checklists", data={"name": name}
        )
        return Checklist.model_validate(result)
