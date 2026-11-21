"""Project-scoped full-text retrieval for the private project assistant."""

import re

from django.db import connection
from django.db.models import Q


def search_queryset(queryset, question, fields, limit=8, order_by=()):
    """Return matching rows, using PostgreSQL FTS or a small SQLite fallback."""
    if connection.vendor == 'postgresql':
        from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector

        vector = SearchVector(fields[0], config='simple')
        for field in fields[1:]:
            vector += SearchVector(field, config='simple')
        search_query = SearchQuery(question, search_type='websearch', config='simple')
        return list(
            queryset.annotate(_project_search_rank=SearchRank(vector, search_query))
            .filter(_project_search_rank__gt=0)
            .order_by('-_project_search_rank', *order_by)[:limit]
        )

    # SQLite is useful for local tests and lightweight development. Production
    # PostgreSQL uses its native tsvector ranking above.
    terms = list(dict.fromkeys(re.findall(r'[\w@.-]{2,}', question.casefold())))
    if not terms:
        return []
    matches = Q()
    for term in terms:
        for field in fields:
            matches |= Q(**{f'{field}__icontains': term})
    candidates = list(queryset.filter(matches).order_by(*order_by)[:max(limit * 12, limit)])

    def field_text(item, field):
        value = item
        for part in field.split('__'):
            value = getattr(value, part, None)
            if value is None:
                return ''
        return str(value).casefold()

    candidates.sort(
        key=lambda item: sum(
            term in ' '.join(field_text(item, field) for field in fields)
            for term in terms
        ),
        reverse=True,
    )
    return candidates[:limit]
