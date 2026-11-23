"""Target suite: a remote shell on the appliance runs a command."""

import uuid

from board_test import BoardTest


class TestRemoteShell(BoardTest):
    """A remote shell on the appliance runs a command."""

    def test_remote_shell_runs_a_command(self) -> None:
        """TST022: from the test host, open a remote shell on the appliance and run a command in it."""
        self.record(requirement="TST022")
        nonce = uuid.uuid4().hex

        output = self.board.in_a_new_shell(f"echo {nonce}")

        self.record(output=output)
        assert output == nonce, f"the command did not run: the shell returned {output!r}"
