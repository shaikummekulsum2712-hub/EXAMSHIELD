"""
ExamShield KMP - the algorithm file.

Everything about string matching lives here:
  build_lps()          the KMP failure table (the "LPS" array)
  kmp_search()         KMP over a whole text, counts character comparisons
  brute_force_search() the naive method, counts character comparisons
  StreamKMP            KMP that receives ONE token at a time (what the server uses)
  StreamBrute          the naive method in the same streaming setting (for comparison)

A "text" here is a student's event stream, one letter per event:
  C = copied text        B = left the exam window (blur)      I = came back after more than 5 s
  P = pasted text        A = answered within 2.5 s of coming back        N = a normal action
"""
from collections import deque

# The cheating signatures the proctor looks for.
SIGNATURES = {
    "CBIA": "Copy the question -> switch away -> read the AI answer -> instant answer",
    "BIA":  "Overlay / Circle to Search -> read the answer -> instant answer",
    "BPBP": "Split-screen copy-paste loop (leave, paste, leave, paste)",
}


def build_lps(pattern):
    """
    LPS[i] = length of the longest proper prefix of pattern[0..i] that is also a suffix of it.
    Example: BPBP -> [0, 0, 1, 2]   (after matching BPB, a mismatch can fall back to 'B' already matched).
    Takes O(m): k only goes up by 1 per step, and every fallback lowers it.
    """
    lps = [0] * len(pattern)
    k = 0
    for i in range(1, len(pattern)):
        while k > 0 and pattern[i] != pattern[k]:
            k = lps[k - 1]
        if pattern[i] == pattern[k]:
            k += 1
        lps[i] = k
    return lps


def kmp_search(text, pattern):
    """Returns (list of start positions of every match, number of character comparisons)."""
    lps = build_lps(pattern)
    m = len(pattern)
    k = 0                      # how many characters of the pattern are matched right now
    comparisons = 0
    found = []
    for i, ch in enumerate(text):
        while True:
            comparisons += 1
            if ch == pattern[k]:
                k += 1
                break
            if k == 0:
                break
            k = lps[k - 1]     # fall back inside the PATTERN - the text pointer never moves back
        if k == m:
            found.append(i - m + 1)
            k = lps[k - 1]     # keep going: overlapping matches are found too
    return found, comparisons


def brute_force_search(text, pattern):
    """Returns (list of start positions of every match, number of character comparisons)."""
    n, m = len(text), len(pattern)
    comparisons = 0
    found = []
    for s in range(n - m + 1):
        j = 0
        while j < m:
            comparisons += 1
            if text[s + j] != pattern[j]:
                break
            j += 1
        if j == m:
            found.append(s)
    return found, comparisons


class StreamKMP:
    """
    KMP for a live stream. The ONLY thing it remembers about the past is one number, `state`
    (how many pattern characters are matched). No buffer, no history, O(1) memory per student.
    """

    def __init__(self, pattern):
        self.pattern = pattern
        self.lps = build_lps(pattern)
        self.state = 0
        self.comparisons = 0
        self.matches = 0

    def feed(self, ch):
        """Gives the matcher the next event. Returns True if the pattern was just completed."""
        m = len(self.pattern)
        while True:
            self.comparisons += 1
            if ch == self.pattern[self.state]:
                self.state += 1
                break
            if self.state == 0:
                break
            self.state = self.lps[self.state - 1]
        if self.state == m:
            self.matches += 1
            self.state = self.lps[self.state - 1]
            return True
        return False


class StreamBrute:
    """
    The naive method on a live stream: it must KEEP the last m events and compare the whole
    window against the pattern after every new event. Same answers, but needs a buffer and
    makes more comparisons.
    """

    def __init__(self, pattern):
        self.pattern = pattern
        self.window = deque(maxlen=len(pattern))
        self.comparisons = 0
        self.matches = 0

    def feed(self, ch):
        self.window.append(ch)
        m = len(self.pattern)
        if len(self.window) < m:
            return False
        for j in range(m):
            self.comparisons += 1
            if self.window[j] != self.pattern[j]:
                return False
        self.matches += 1
        return True
