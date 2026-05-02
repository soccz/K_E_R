"""_watchlist.md의 표를 파싱하여 종목 리스트로 변환."""
from dataclasses import dataclass


@dataclass(frozen=True)
class WatchlistEntry:
    name: str
    ticker: str
    corp_code: str | None
    sector: str
    note: str


def parse_watchlist(md_text: str) -> list[WatchlistEntry]:
    entries: list[WatchlistEntry] = []
    in_table = False
    for line in md_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("| #"):
            in_table = True
            continue
        if in_table and stripped.startswith("|---"):
            continue
        if not in_table:
            continue
        if not stripped.startswith("|"):
            in_table = False
            continue

        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        if len(cells) < 6:
            continue
        if not cells[0].isdigit():
            continue

        corp_code = cells[3] if cells[3].upper() != "TBD" else None
        entries.append(
            WatchlistEntry(
                name=cells[1],
                ticker=cells[2],
                corp_code=corp_code,
                sector=cells[4],
                note=cells[5],
            )
        )
    return entries


def find_by_ticker(entries: list[WatchlistEntry], ticker: str) -> WatchlistEntry | None:
    for e in entries:
        if e.ticker == ticker:
            return e
    return None


def find_by_name(entries: list[WatchlistEntry], name: str) -> WatchlistEntry | None:
    for e in entries:
        if e.name == name:
            return e
    return None
