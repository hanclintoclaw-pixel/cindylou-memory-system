"""Explicit private legacy JSONL import; originals retained, never promoted.

The exact log and each original row are immutable source snapshots. Row-byte
identities keep retries stable even if the source log later appends/reorders.
Original confidence/source/visibility labels are preserved as source metadata,
not trusted authorization, canon or independent corroboration.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime, timezone

from .capture import CaptureStore, _tokens
from .policy import AccessContext, AccessDenied, StaleReference


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _private_dir(path):
    path = Path(path)
    if not path.is_absolute() or path.resolve() != path or path.is_symlink():
        raise ValueError('canonical private import root required')
    path.mkdir(parents=True,mode=0o700,exist_ok=True)
    if path.stat().st_mode & 0o077:
        raise ValueError('import root must be private')
    return path


def _snapshot(path, raw):
    """Atomic exclusive publication of a complete snapshot; races cannot see partials."""
    path = Path(path)
    lock = os.open(path.parent/'.snapshot.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    temporary = None
    try:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if path.is_symlink():
            raise ValueError('immutable import snapshot differs')
        if path.exists():
            if path.stat().st_mode & 0o077 or path.read_bytes() != raw:
                raise ValueError('immutable import snapshot differs')
            return
        fd, temporary = tempfile.mkstemp(prefix='.import-',dir=path.parent)
        with os.fdopen(fd,'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        # Some data volumes do not support hard links. Cooperative directory
        # locking plus same-directory rename gives complete exclusive publication.
        os.replace(temporary,path)
        directory = os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
        fcntl.flock(lock,fcntl.LOCK_UN)
        os.close(lock)


def import_jsonl(source, store: CaptureStore, archive_root, ctx: AccessContext):
    ctx.check()
    if ctx.audience != 'operator':
        raise AccessDenied('not authorized')
    source = Path(source)
    if not source.is_absolute() or source.is_symlink() or source.resolve() != source:
        raise ValueError('canonical original source required')
    before_stat = source.stat()
    raw = source.read_bytes()
    after_stat = source.stat()
    if (before_stat.st_ino,before_stat.st_size,before_stat.st_mtime_ns) != (
            after_stat.st_ino,after_stat.st_size,after_stat.st_mtime_ns):
        raise StaleReference('legacy log changed during source capture')
    source_revision = _sha(raw)
    archive = _private_dir(archive_root)
    originals = _private_dir(archive/'originals')
    rows_path = _private_dir(archive/'rows')
    receipts_path = _private_dir(archive/'receipts')
    _snapshot(originals/(source_revision+'.jsonl'),raw)
    initial_count = store.recover()['saved_records']
    rows = []
    for number, row in enumerate(raw.splitlines(),1):
        if not row.strip():
            rows.append({'source_line':number,'status':'blank'})
            continue
        row_revision = _sha(row)
        _snapshot(rows_path/(row_revision+'.json'),row)
        try:
            value = json.loads(row)
        except (ValueError,UnicodeDecodeError):
            rows.append({'source_line':number,'row_revision':row_revision,'status':'quarantined',
                         'reason':'invalid-json'})
            continue
        text = (value.get('fact') or value.get('text')) if isinstance(value,dict) else None
        if (not isinstance(text,str) or not text.strip() or len(text)>32000 or
                not any(len(token)<=4000 for token in _tokens(text))):
            rows.append({'source_line':number,'row_revision':row_revision,'status':'quarantined',
                         'reason':'missing-or-invalid-fact-text'})
            continue
        # No visibility/status/confidence input from the historical row can
        # promote or widen this new private/provisional capture.
        origin = {'doc_id':'legacy-chat-facts/rows/'+row_revision+'.json',
                  'revision':row_revision,'record_id':row_revision,'kind':'legacy-jsonl-row',
                  'start_line':1,'end_line':1}
        receipt = store.capture(text,ctx,idempotency_key='legacy-chat-facts/v1/'+row_revision,
                                origin=origin,visibility='operator')
        rows.append({'source_line':number,'row_revision':row_revision,'status':'captured',
                     'receipt':receipt})
    # A concurrent append does not invalidate the immutable imported snapshot,
    # but it must be reported rather than implying the entire current log is done.
    current_revision = _sha(source.read_bytes())
    ctx.check()
    final = store.recover()
    report = {'version':1,'source_path':str(source),'source_revision':source_revision,
              'original_snapshot':str(originals/(source_revision+'.jsonl')),
              'source_changed_after_snapshot':current_revision!=source_revision,
              'rows':rows,'physical_lines':len(raw.splitlines()),
              'captured_rows':sum(r['status']=='captured' for r in rows),
              'quarantined_rows':sum(r['status']=='quarantined' for r in rows),
              'blank_rows':sum(r['status']=='blank' for r in rows),
              'new_records':sum(r['receipt']['created'] for r in rows if r['status']=='captured'),
              'observed_store_delta':final['saved_records']-initial_count,
              'saved_records':final['saved_records'],'searchable_records':final['searchable_records'],
              'promoted_records':0,'visibility':'operator','claim_status':'provisional',
              'note':'Original fields retained in exact immutable source/row snapshots; no provenance or public authority inferred.'}
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    report_path = receipts_path/(stamp+'.private.json')
    _snapshot(report_path,(json.dumps(report,indent=2)+'\n').encode())
    report['receipt_path'] = str(report_path)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--store',type=Path,required=True)
    parser.add_argument('--archive',type=Path,required=True)
    args = parser.parse_args()
    os.umask(0o077)
    report = import_jsonl(args.source,CaptureStore(args.store),args.archive,AccessContext('operator'))
    # Local command is operator-only; still keep fact text out of receipts/stdout.
    print(json.dumps({k:report[k] for k in ('receipt_path','physical_lines','captured_rows',
        'quarantined_rows','new_records','saved_records','searchable_records','promoted_records',
        'source_changed_after_snapshot')}))


if __name__=='__main__':
    main()
