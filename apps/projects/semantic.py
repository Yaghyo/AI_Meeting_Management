"""Project-scoped semantic retrieval using OpenAI embeddings and pgvector."""

import hashlib
import json
import logging
import os
import re

from django.db import connection

from apps.meetings.models import ActionItem, MeetingAIReport, TranscriptLine
from .models import GroupMessage, ProjectKnowledgeChunk, ProjectGroup


logger = logging.getLogger(__name__)
EMBEDDING_MODEL = 'text-embedding-3-small'
EMBEDDING_DIMENSIONS = 1536
CHUNK_LENGTH = 1400
CHUNK_OVERLAP = 180


def split_text(text):
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(len(text), start + CHUNK_LENGTH)
        if end < len(text):
            boundary = text.rfind(' ', start + CHUNK_LENGTH // 2, end)
            if boundary > start:
                end = boundary
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(text):
            break
        start = max(start + 1, end - CHUNK_OVERLAP)
    return chunks


def pgvector_available():
    if connection.vendor != 'postgresql':
        return False
    with connection.cursor() as cursor:
        cursor.execute("SELECT EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector')")
        return cursor.fetchone()[0]


def _source_documents(project_id):
    reports = MeetingAIReport.objects.filter(meeting__project_id=project_id).select_related('meeting')
    for report in reports.iterator():
        meeting = report.meeting
        content = '\n'.join(part for part in (
            f'Summary: {report.summary}',
            f'Key points: {"; ".join(map(str, report.key_points))}',
            f'Decisions: {"; ".join(map(str, report.decisions))}',
            f'Project updates: {"; ".join(map(str, report.project_updates))}',
            f'Project description: {report.project_description}',
        ) if part.strip())
        yield (
            ProjectKnowledgeChunk.SourceType.MEETING_SUMMARY,
            f'meeting-summary:{meeting.pk}',
            f'Meeting summary: {meeting.title} · {meeting.scheduled_at:%Y-%m-%d}',
            content,
        )

    lines = TranscriptLine.objects.filter(meeting__project_id=project_id).select_related('meeting', 'speaker')
    for line in lines.iterator():
        speaker = (line.speaker.get_full_name() or line.speaker.username) if line.speaker else 'Unknown speaker'
        yield (
            ProjectKnowledgeChunk.SourceType.TRANSCRIPT,
            f'transcript:{line.pk}',
            f'Transcript: {line.meeting.title} · {line.spoken_at:%Y-%m-%d %H:%M} · {speaker}',
            line.text,
        )

    group_ids = ProjectGroup.objects.filter(project_id=project_id).values_list('pk', flat=True)
    messages = GroupMessage.objects.filter(group_id__in=group_ids).select_related('sender')
    for message in messages.iterator():
        yield (
            ProjectKnowledgeChunk.SourceType.GROUP_MESSAGE,
            f'group-message:{message.pk}',
            f'Project chat: {message.created_at:%Y-%m-%d %H:%M} · {message.sender.get_full_name() or message.sender.username}',
            message.body,
        )

    tasks = ActionItem.objects.filter(meeting__project_id=project_id).select_related('meeting', 'assigned_to')
    for task in tasks.iterator():
        owner = (task.assigned_to.get_full_name() or task.assigned_to.username) if task.assigned_to else task.suggested_assignee or 'Unassigned'
        content = (
            f'Task: {task.title}\nDescription: {task.description}\nOwner: {owner}\n'
            f'Status: {task.get_status_display()}\nPriority: {task.get_priority_display()}\n'
            f'Due date: {task.due_date.isoformat() if task.due_date else "not set"}\nEvidence: {task.evidence}'
        )
        yield (
            ProjectKnowledgeChunk.SourceType.ACTION_ITEM,
            f'action-item:{task.pk}',
            f'Task #{task.pk}: {task.meeting.title}',
            content,
        )


def _sync_project_chunks(project_id):
    source_keys = []
    pending = []
    for source_type, source_key, label, content in _source_documents(project_id):
        for index, chunk_text in enumerate(split_text(content)):
            chunk_key = f'{source_key}:{index}'
            source_keys.append(chunk_key)
            digest = hashlib.sha256(chunk_text.encode('utf-8')).hexdigest()
            chunk, created = ProjectKnowledgeChunk.objects.get_or_create(
                project_id=project_id,
                source_key=chunk_key,
                defaults={
                    'source_type': source_type,
                    'source_label': label,
                    'content': chunk_text,
                    'content_hash': digest,
                },
            )
            if not created and (chunk.content_hash != digest or chunk.embedding_model != EMBEDDING_MODEL):
                chunk.source_type = source_type
                chunk.source_label = label
                chunk.content = chunk_text
                chunk.content_hash = digest
                chunk.embedding = None
                chunk.embedding_model = ''
                chunk.save(update_fields=(
                    'source_type', 'source_label', 'content', 'content_hash',
                    'embedding', 'embedding_model', 'updated_at',
                ))
            if chunk.embedding is None or chunk.embedding_model != EMBEDDING_MODEL:
                pending.append(chunk)

    # Remove chunks for source rows that were deleted from this project.
    stale = ProjectKnowledgeChunk.objects.filter(project_id=project_id)
    if source_keys:
        stale.exclude(source_key__in=source_keys).delete()
    else:
        stale.delete()

    if not pending:
        return
    from openai import OpenAI

    client = OpenAI(api_key=os.environ['OPENAI_API_KEY'].strip())
    for offset in range(0, len(pending), 64):
        batch = pending[offset:offset + 64]
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=[chunk.content for chunk in batch],
        )
        ordered = sorted(response.data, key=lambda item: item.index)
        for chunk, item in zip(batch, ordered):
            if len(item.embedding) != EMBEDDING_DIMENSIONS:
                raise ValueError('The configured embedding model returned an unexpected vector size.')
            chunk.embedding = item.embedding
            chunk.embedding_model = EMBEDDING_MODEL
        ProjectKnowledgeChunk.objects.bulk_update(batch, ('embedding', 'embedding_model', 'updated_at'))


def retrieve_semantic_context(project_id, question, limit=8):
    """Build/update a project's vector index and return its closest source chunks."""
    api_key = os.environ.get('OPENAI_API_KEY', '').strip()
    if not api_key or not pgvector_available():
        return []

    try:
        _sync_project_chunks(project_id)
        from openai import OpenAI

        query_embedding = OpenAI(api_key=api_key).embeddings.create(
            model=EMBEDDING_MODEL,
            input=[question[:8000]],
        ).data[0].embedding
        if len(query_embedding) != EMBEDDING_DIMENSIONS:
            raise ValueError('The configured embedding model returned an unexpected vector size.')
        vector_literal = json.dumps(query_embedding, separators=(',', ':'))
        table = ProjectKnowledgeChunk._meta.db_table
        sql = f'''
            SELECT id
            FROM {connection.ops.quote_name(table)}
            WHERE project_id = %s AND embedding IS NOT NULL AND embedding_model = %s
            ORDER BY (embedding::text)::vector({EMBEDDING_DIMENSIONS}) <=> %s::vector
            LIMIT %s
        '''
        with connection.cursor() as cursor:
            cursor.execute(sql, (project_id, EMBEDDING_MODEL, vector_literal, limit))
            ids = [row[0] for row in cursor.fetchall()]
        chunks = ProjectKnowledgeChunk.objects.in_bulk(ids)
        return [chunks[chunk_id] for chunk_id in ids if chunk_id in chunks]
    except Exception:
        logger.exception('Semantic retrieval failed for project %s; project full-text search remains available.', project_id)
        return []
