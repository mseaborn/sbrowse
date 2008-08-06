
import unittest

import sbrowse


class Test(unittest.TestCase):

    def test(self):
        self.assertEquals(list(sbrowse.tokens("  foo !! bar31 + _qux && ")),
                          [("  ", False), 
                           ("foo", True), 
                           (" !! ", False), 
                           ("bar31", True),
                           (" + ", False), 
                           ("_qux", True), 
                           (" && ", False)])


if __name__ == "__main__":
    unittest.main()
