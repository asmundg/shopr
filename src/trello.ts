const root = "https://api.trello.com";

interface Board {
  id: string;
  desc: string;
  descData: string;
  closed: boolean;
  idOrganization: string;
  pinned: boolean;
  url: string;
  shortUrl: string;
  prefs: {
    permissionLevel: string;
    hideVotes: boolean;
    voting: "disabled";
    comments: string;
    selfJoin: boolean;
    cardCovers: boolean;
    isTemplate: boolean;
    cardAging: "pirate";
    calendarFeedEnabled: boolean;
    background: string;
    backgroundImage: string;
    backgroundImageScaled: string;
  };
  labelNames: {
    green: string;
    yellow: string;
    orange: string;
    red: string;
    purple: string;
    blue: string;
    sky: string;
    lime: string;
    pink: string;
    black: string;
  };
  limits: {
    attachments: {
      perBoard: {
        status: "ok";
        disableAt: number;
        warnAt: number;
      };
    };
  };
  starred: boolean;
  memberships: string;
  shortLink: string;
  subscribed: boolean;
  powerUps: string;
  dateLastActivity: string;
  dateLastView: string;
  idTags: string;
  datePluginDisable: string;
  creationMethod: string;
  ixUpdate: number;
  templateGallery: string;
  enterpriseOwned: boolean;
}

interface Card {
  id: string;
  address: string;
  badges: {
    attachmentsByType: {
      trello: {
        board: number;
        card: number;
      };
    };
    location: boolean;
    votes: number;
    viewingMemberVoted: boolean;
    subscribed: boolean;
    fogbugz: string;
    checkItems: number;
    checkItemsChecked: number;
    comments: number;
    attachments: number;
    description: boolean;
    due: string;
    dueComplete: boolean;
  };
  checkItemStates: [string];
  closed: boolean;
  coordinates: string;
  creationMethod: string;
  dateLastActivity: string;
  desc: string;
  descData: {
    emoji: {};
  };
  due: string;
  dueReminder: string;
  email: string;
  idBoard: string;
  idChecklists: string[];
  idLabels: string[];
  idList: string;
  idMembers: [string];
  idMembersVoted: [string];
  idShort: number;
  labels: {
    id: string;
    idBoard: string;
    name: string;
    color: string;
  }[];
  limits: {
    attachments: {
      perBoard: {
        status: string;
        disableAt: number;
        warnAt: number;
      };
    };
  };
  locationName: string;
  manualCoverAttachment: boolean;
  name: string;
  pos: number;
  shortLink: string;
  shortUrl: string;
  subscribed: boolean;
  url: string;
  cover: {
    color: string;
    idUploadedBackground: boolean;
    size: string;
    brightness: string;
    isTemplate: boolean;
  };
}

export interface ChecklistItem {
  idChecklist: string;
  state: "complete";
  idMember: null;
  id: string;
  name: string;
  nameData: null;
  pos: number;
  due: null;
}

export interface Checklist {
  id: string;
  name: string;
  idCard: string;
  pos: number;
  idBoard: string;
  checkItems: ChecklistItem[];
}

export type TrelloClient = ReturnType<typeof trello>;
export interface RequestFactory {
  (
    method: "get" | "delete" | "post" | "put",
    url: string,
    params: {},
    data?: unknown
  ): Promise<{}>;
}

export const trello = (opts: {
  key: string;
  token: string;
  makeRequest: RequestFactory;
}) => {
  const { key, token, makeRequest } = opts;

  return {
    getBoard: (id: string) =>
      makeRequest("get", `${root}/1/boards/${id}`, { key, token }) as Promise<
        Board
      >,
    getBoardChecklists: (id: string) =>
      makeRequest("get", `${root}/1/boards/${id}/checklists`, {
        key,
        token,
        fields: "all",
      }) as Promise<Board>,
    getBoardCards: (id: string) =>
      makeRequest("get", `${root}/1/boards/${id}/cards`, {
        key,
        token,
      }) as Promise<Card[]>,
    getCard: (id: string) =>
      makeRequest("get", `${root}/1/cards/${id}`, { key, token }) as Promise<
        Card
      >,

    getChecklist: (id: string) =>
      makeRequest("get", `${root}/1/checklists/${id}`, {
        key,
        token,
      }) as Promise<Checklist>,
    updateChecklist: (id: string, data: Checklist) =>
      makeRequest("put", `${root}/1/checklists/${id}`, { key, token }, data),

    updateChecklistItem: (
      idCard: string,
      idChecklist: string,
      idCheckItem: string,
      data: ChecklistItem
    ) =>
      makeRequest(
        "put",
        `${root}/1/cards/${idCard}/checklist/${idChecklist}/checkItem/${idCheckItem}`,
        { key, token },
        data
      ),

    // Add a checklist item to a checklist
    addChecklistItem: (
      idChecklist: string,
      name: string,
      pos?: number
    ) =>
      makeRequest(
        "post",
        `${root}/1/checklists/${idChecklist}/checkItems`,
        { key, token },
        { name, pos }
      ) as Promise<ChecklistItem>,

    // Get cards in a specific list
    getListCards: (idList: string) =>
      makeRequest("get", `${root}/1/lists/${idList}/cards`, {
        key,
        token,
      }) as Promise<Card[]>,

    // Move a card to a different list
    moveCardToList: (idCard: string, idList: string) =>
      makeRequest(
        "put",
        `${root}/1/cards/${idCard}`,
        { key, token },
        { idList }
      ),

    removeLabel: (idCard: string, idLabel: string) =>
      makeRequest("delete", `${root}/1/cards/${idCard}/idLabels/${idLabel}`, {
        key,
        token,
      }),

    // Get all lists on a board
    getBoardLists: (idBoard: string) =>
      makeRequest("get", `${root}/1/boards/${idBoard}/lists`, {
        key,
        token,
      }),

    // Create a new checklist on a card
    createChecklist: (idCard: string, name: string = "Checklist") =>
      makeRequest(
        "post",
        `${root}/1/cards/${idCard}/checklists`,
        { key, token },
        { name }
      ) as Promise<Checklist>,
  };
};
