import { parseItemName, formatItemName } from "../shopr";

describe("parseItemName", () => {
  describe("items with quantities", () => {
    it("should parse item name with quantity", () => {
      const result = parseItemName("eggs 2");
      expect(result).toEqual({ base: "eggs", quantity: 2 });
    });

    it("should parse item name with large quantity", () => {
      const result = parseItemName("apples 10");
      expect(result).toEqual({ base: "apples", quantity: 10 });
    });

    it("should parse multi-word item with quantity", () => {
      const result = parseItemName("green beans 3");
      expect(result).toEqual({ base: "green beans", quantity: 3 });
    });

    it("should parse item with extra spaces before quantity", () => {
      const result = parseItemName("milk  5");
      expect(result).toEqual({ base: "milk", quantity: 5 });
    });
  });

  describe("items without quantities", () => {
    it("should default quantity to 1 for item without number", () => {
      const result = parseItemName("eggs");
      expect(result).toEqual({ base: "eggs", quantity: 1 });
    });

    it("should handle multi-word items without quantity", () => {
      const result = parseItemName("green beans");
      expect(result).toEqual({ base: "green beans", quantity: 1 });
    });

    it("should handle items with numbers in the middle", () => {
      const result = parseItemName("coffee 100g");
      expect(result).toEqual({ base: "coffee 100g", quantity: 1 });
    });
  });

  describe("edge cases", () => {
    it("should trim whitespace from item names", () => {
      const result = parseItemName("  eggs  ");
      expect(result).toEqual({ base: "eggs", quantity: 1 });
    });

    it("should trim whitespace from item with quantity", () => {
      const result = parseItemName("  milk 2  ");
      expect(result).toEqual({ base: "milk", quantity: 2 });
    });

    it("should handle single letter item", () => {
      const result = parseItemName("x");
      expect(result).toEqual({ base: "x", quantity: 1 });
    });

    it("should handle single letter item with quantity", () => {
      const result = parseItemName("x 5");
      expect(result).toEqual({ base: "x", quantity: 5 });
    });

    it("should handle items ending with parenthetical numbers", () => {
      const result = parseItemName("eggs (2)");
      expect(result).toEqual({ base: "eggs (2)", quantity: 1 });
    });
  });
});

describe("formatItemName", () => {
  describe("quantity of 1", () => {
    it("should return just the base name for quantity 1", () => {
      const result = formatItemName("eggs", 1);
      expect(result).toBe("eggs");
    });

    it("should handle multi-word items with quantity 1", () => {
      const result = formatItemName("green beans", 1);
      expect(result).toBe("green beans");
    });
  });

  describe("quantity greater than 1", () => {
    it("should append quantity for quantity > 1", () => {
      const result = formatItemName("eggs", 2);
      expect(result).toBe("eggs 2");
    });

    it("should handle large quantities", () => {
      const result = formatItemName("apples", 100);
      expect(result).toBe("apples 100");
    });

    it("should handle multi-word items with quantity", () => {
      const result = formatItemName("green beans", 3);
      expect(result).toBe("green beans 3");
    });
  });

  describe("edge cases", () => {
    it("should handle empty string with quantity 1", () => {
      const result = formatItemName("", 1);
      expect(result).toBe("");
    });

    it("should handle empty string with quantity > 1", () => {
      const result = formatItemName("", 5);
      expect(result).toBe(" 5");
    });

    it("should handle single character item", () => {
      const result = formatItemName("x", 3);
      expect(result).toBe("x 3");
    });
  });
});

describe("parseItemName and formatItemName integration", () => {
  it("should be reversible for items with quantity > 1", () => {
    const original = "eggs 3";
    const parsed = parseItemName(original);
    const formatted = formatItemName(parsed.base, parsed.quantity);
    expect(formatted).toBe(original);
  });

  it("should be reversible for items with quantity 1", () => {
    const original = "eggs";
    const parsed = parseItemName(original);
    const formatted = formatItemName(parsed.base, parsed.quantity);
    expect(formatted).toBe(original);
  });

  it("should handle round-trip with multi-word items", () => {
    const original = "green beans 5";
    const parsed = parseItemName(original);
    const formatted = formatItemName(parsed.base, parsed.quantity);
    expect(formatted).toBe(original);
  });

  it("should normalize items without explicit quantity", () => {
    const original = "milk";
    const parsed = parseItemName(original);
    // Adding 1 to quantity of 1 gives 2
    const formatted = formatItemName(parsed.base, parsed.quantity + 1);
    expect(formatted).toBe("milk 2");
  });
});
