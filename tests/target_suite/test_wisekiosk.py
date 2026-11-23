"""Target suite: the WiseKiosk instance's page is served."""

from board_test import BoardTest


class TestWisekiosk(BoardTest):
    """The instance's page is served."""

    def test_page_serves(self) -> None:
        """TST022: the WiseKiosk instance's page is served on the appliance."""
        fetch = self.board.app.page.fetch()

        assert fetch.returncode == 0, f"GET / failed (rc {fetch.returncode}): {fetch.output}"
        assert "<html" in fetch.output, f"GET / did not return an <html> body: {fetch.output}"
        self.record(requirement="TST022")
