"""Simple ELO ranking implementation."""


class EloRank:
    """Simple ELO ranking system."""

    def __init__(self, k_factor: int = 32):
        """Initialize ELO ranking system.

        Args:
            k_factor: K-factor for ELO calculation (default: 32)
        """
        self.k_factor = k_factor

    def get_expected(self, rating_a: float, rating_b: float) -> float:
        """Get expected score for player A against player B.

        Args:
            rating_a: Rating of player A
            rating_b: Rating of player B

        Returns:
            Expected score (0-1)
        """
        return 1 / (1 + 10 ** ((rating_b - rating_a) / 400))

    def update_rating(
        self,
        expected: float,
        actual: float,
        current: float,
    ) -> float:
        """Update rating based on match result.

        Args:
            expected: Expected score (0-1)
            actual: Actual score (0 for loss, 1 for win)
            current: Current rating

        Returns:
            New rating
        """
        return current + self.k_factor * (actual - expected)
