import traceback

from . import Tweet, Excel, User, List
from .base import BaseGeneratorClass
from .twDataTypes import SelfThread
from ..utils import find_objects
from ..filters import SearchFilters


class Search(BaseGeneratorClass):
    OBJECTS_TYPES = {
        "tweet": Tweet,
        "search": Tweet,
        "homeConversation": SelfThread,
        "profile": SelfThread,
        "user": User,
        "list": List
    }
    _RESULT_ATTR = "results"

    def __init__(self, keyword, client, pages=1, filter_=None, wait_time=2, cursor=None):
        super().__init__()
        self.results = []
        self.keyword = keyword
        self.cursor = cursor
        self.cursor_top = cursor
        self.is_next_page = True
        self.client = client
        self.pages = pages
        self.wait_time = wait_time
        self.filter = filter_.strip() if filter_ else None

    def __repr__(self):
        return "Search(keyword={}, count={}, filter={})".format(
            self.keyword, len(self.results), self.filter
        )

    async def get_page(self, cursor):
        thisObjects = []
        response = await self.client.http.perform_search(self.keyword, cursor, self.filter)
        entries = self._get_entries(response)

        if self.filter == SearchFilters.Lists:
            entries = self._get_list_entries(entries)
        elif self.filter == SearchFilters.Media:
            entries = self._get_grid_entries(entries)

        for entry in entries:
            object_type = self._get_target_object(entry)
            try:
                if object_type is None:
                    continue
                parsed = object_type(self.client, entry, None)
                if parsed:
                    thisObjects.append(parsed)
            except:
                pass
        cursor = self._get_cursor_(response)
        cursor_top = self._get_cursor_(response, "Top")

        return thisObjects, cursor, cursor_top

    def _get_target_object(self, obj):
        entry_type = str(obj['entryId']).split("-")[0]
        return self.OBJECTS_TYPES.get(entry_type)

    @staticmethod
    def _get_grid_entries(entries):
        results = []
        for entry in entries:
            obj = find_objects(entry, "displayType", "VerticalGrid", none_value={}, recursive=False)
            if obj:
                results.extend(obj.get("items", []))
        return results

    @staticmethod
    def _get_list_entries(entries):
        results = []
        for entry in entries:
            if str(entry['entryId']).split("-")[0] == "list":
                for item in entry['content']['items']:
                    results.append(item)
        return results

    def to_xlsx(self, filename=None):
        if self.filter == "users":
            return AttributeError("to_xlsx with 'users' filter isn't supported yet")

        return Excel(self.results, f"search-{self.keyword}", filename)


class RadarSearch(BaseGeneratorClass):
    """
    Wraps the postListQuery endpoint (x.com's "radar" search — the same one
    powering the Top/Latest tabs on x.com/search), as opposed to Search's
    older SearchTimeline endpoint.

    This endpoint uses a noticeably different (newer) entry schema than
    SearchTimeline: entries have no top-level "entryId" (content is typed via
    nested "__typename" chains instead — TimelineTimelineItem/TimelineTweet/
    TimelineTimelineCursor), and cursors use "cursor_type" (snake_case)
    rather than "cursorType". So this class parses entries/cursors itself
    instead of reusing Search's entryId-prefix-based helpers.
    """
    _CONTENT_TYPE_MAP = {
        "TimelineTweet": Tweet,
        "TimelineUser": User,
    }
    _RESULT_ATTR = "results"

    def __init__(self, query, client, pages=1, product="Top", wait_time=2, cursor=None):
        super().__init__()
        self.results = []
        self.query = query
        self.cursor = cursor
        self.cursor_top = cursor
        self.is_next_page = True
        self.client = client
        self.pages = pages
        self.wait_time = wait_time
        self.product = product or "Top"

    def __repr__(self):
        return "RadarSearch(query={}, count={}, product={})".format(
            self.query, len(self.results), self.product
        )

    async def get_page(self, cursor):
        thisObjects = []
        response = await self.client.http.radar_search(self.query, cursor, self.product)

        add_entries = find_objects(response, "__typename", "TimelineAddEntries")
        entries = add_entries.get("entries", []) if add_entries else []

        for entry in entries:
            object_type = self._get_target_object(entry)
            if object_type is None:
                continue
            try:
                parsed = object_type(self.client, entry, None)
                if parsed:
                    thisObjects.append(parsed)
            except Exception:
                pass

        cursor = self._get_radar_cursor(response, "Bottom")
        cursor_top = self._get_radar_cursor(response, "Top")

        return thisObjects, cursor, cursor_top

    @staticmethod
    def _get_target_object(entry):
        content = entry.get("content") or {}
        if content.get("__typename") != "TimelineTimelineItem":
            return None
        inner_typename = (content.get("content") or {}).get("__typename")
        return RadarSearch._CONTENT_TYPE_MAP.get(inner_typename)

    @staticmethod
    def _get_radar_cursor(response, cursor_type):
        cursor = find_objects(response, "cursor_type", cursor_type, none_value={})
        return cursor.get("value")

    def to_xlsx(self, filename=None):
        return Excel(self.results, f"radar-search-{self.query}", filename)


class TypeHeadSearch(dict):
    DATA_TYPES = {
        "users": User
    }

    def __init__(self, client, keyword, result_type='events,users,topics,lists'):
        super().__init__()
        self.client = client
        self.keyword = keyword
        self.result_type = result_type
        self.results = []

    async def get_results(self):
        response = await self.client.http.search_typehead(self.keyword, self.result_type)
        for _type_name, _type_object in self.DATA_TYPES.items():
            for result in response.get(_type_name, []):
                try:
                    if _type_name == "users":
                        result['__typename'] = "User"

                    parsed = _type_object(self.client, result)
                    self.results.append(parsed)
                except:
                    pass
        self['results'] = self.results
        return self.results

    def __getitem__(self, index):
        if isinstance(index, str):
            return getattr(self, index)

        return self.results[index]

    def __iter__(self):
        for i in self.results:
            yield i

    def __len__(self):
        return len(self.results)

    def __repr__(self):
        return "TypeHeadSearch(keyword={})".format(self.keyword)

