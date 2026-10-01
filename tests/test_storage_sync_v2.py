from datetime import datetime, timezone
from pathlib import Path
import json
import pytest
from timerapp_ag.storage import AppState, Storage
from timerapp_ag.models import Task, Session, TaskStatus
from timerapp_ag import sync_protocol as protocol


def prepared(tmp_path):
    storage=Storage(tmp_path/'data.json')
    storage.save(AppState(tasks=[Task(id='t',day='2026-01-01',title='Task',result='old',daily_priorities={'2026-01-01':2},keep_priority=True)]))
    storage.enable_sync_v2()
    return storage


def test_clear_known_optional_fields_survives_sync(tmp_path):
    storage=prepared(tmp_path);state=storage.load()
    old=state.sync_v2
    state.tasks[0].result='';state.tasks[0].daily_priorities={};state.tasks[0].keep_priority=False
    storage.save(state);merged=storage.merge_sync_v2(old)
    assert merged.tasks[0].result==''
    assert merged.tasks[0].daily_priorities=={}
    assert merged.tasks[0].keep_priority is False


def test_corrupt_file_never_silently_becomes_empty_or_overwritten(tmp_path):
    path=tmp_path/'data.json';path.write_text('{broken')
    storage=Storage(path)
    with pytest.raises(ValueError, match='повреждён'):
        storage.load()
    assert path.read_text()=='{broken'


def test_explicit_active_choice_keeps_both_sessions_and_rejects_stale_choice(tmp_path):
    storage=prepared(tmp_path)
    state=storage.load();state.tasks[0].sessions=[Session(id='a',started_at='2026-01-01T10:00:00+00:00'),Session(id='b',started_at='2026-01-01T10:05:00+00:00')]
    state.tasks[0].status=TaskStatus.RUNNING;storage.save(state)
    selected=storage.keep_active_session('t','b',expected=[['t','a'],['t','b']],now=datetime(2026,1,1,10,10,tzinfo=timezone.utc))
    sessions=selected.tasks[0].sessions
    assert len(sessions)==2
    assert next(s for s in sessions if s.id=='a').ended_at=='2026-01-01T10:10:00+00:00'
    assert next(s for s in sessions if s.id=='b').ended_at is None
    with pytest.raises(ValueError,match='изменился'):
        storage.keep_active_session('t','b',expected=[['t','a'],['t','b']])


def test_stale_writers_merge_independent_fields_and_retain_same_field_conflict(tmp_path):
    storage=prepared(tmp_path);other=Storage(storage.path)
    a=storage.load();b=other.load()
    a.tasks[0].title='A';storage.save(a)
    b.tasks[0].description='B';other.save(b)
    assert storage.load().tasks[0].title=='A'
    assert storage.load().tasks[0].description=='B'
    a=storage.load();b=other.load()
    a.tasks[0].title='left';storage.save(a)
    b.tasks[0].title='right';other.save(b)
    conflict=next(c for c in protocol.project_document(storage.load().sync_v2)['conflicts'] if c['field']=='title')
    assert {c['value'] for c in conflict['candidates']}=={'left','right'}


def test_stale_writer_cannot_resurrect_deleted_task_and_model_metadata_survives(tmp_path):
    storage=prepared(tmp_path);stale=storage.load()
    state=storage.load();state.tasks=[];storage.save(state)
    stale.tasks[0].description='unsent';storage.save(stale)
    assert storage.load().tasks==[]
    assert any(c['field']=='$alive' for c in protocol.project_document(storage.load().sync_v2)['conflicts'])
    storage.resolve_sync_conflict(['task','t'],'$alive',True)
    state=storage.load();state.tasks[0].extra['future']={'decimal':1.25};storage.save(state)
    assert storage.load().tasks[0].to_dict()['future']=={'decimal':1.25}


def test_restore_old_snapshot_rotates_actor_and_sync_is_idempotent(tmp_path):
    storage=prepared(tmp_path);state=storage.load();state.tasks[0].title='first';storage.save(state)
    snapshot=storage.path.read_bytes();state.tasks[0].title='second';storage.save(state);newer=state.sync_v2
    storage.path.write_bytes(snapshot)
    restored=storage.load();restored.tasks[0].description='after restore';storage.save(restored)
    merged=storage.merge_sync_v2(newer)
    assert merged.tasks[0].title=='second';assert merged.tasks[0].description=='after restore'
    once=merged.sync_v2;assert storage.merge_sync_v2(newer).sync_v2==once


def test_unknown_remote_version_and_io_failure_leave_current_data(tmp_path,monkeypatch):
    storage=prepared(tmp_path);original=storage.path.read_bytes()
    with pytest.raises(ValueError):storage.merge_sync_v2({'format':'tasktimer-sync','version':3,'ops':[]})
    assert storage.path.read_bytes()==original
    def denied(*args,**kwargs):raise OSError('disk full')
    monkeypatch.setattr('timerapp_ag.storage.atomic_write',denied)
    state=storage.load();state.tasks[0].title='edit'
    with pytest.raises(OSError):storage.save(state)
    assert storage.path.read_bytes()==original


def test_remote_b_then_stale_ui_c_retains_both_unseen_values(tmp_path):
    storage=prepared(tmp_path);stale=storage.load()
    remote=protocol.change_entity(stale.sync_v2,'phone',['task','t'],{'title':'B'})
    storage.merge_sync_v2(remote)
    stale.tasks[0].title='C';storage.save(stale)
    conflict=next(c for c in protocol.project_document(storage.load().sync_v2)['conflicts'] if c['field']=='title')
    assert {c['value'] for c in conflict['candidates']}=={'B','C'}


def test_full_pwa_task_schema_keeps_priority_calendar_and_extra_metadata(tmp_path):
    storage=Storage(tmp_path/'data.json');storage.enable_sync_v2()
    tasks=[{'id':'pwa','day':'2026-10-01','title':'PWA','description':'','result':'','status':'paused','created_at':'2026-10-01T10:00:00.123Z','completed_at':None,'priority':2,'daily_priorities':{'2026-10-01':2},'keep_priority':False,'planned_days':['2026-10-01'],'continuation_of':None,'bitrix':{'task_id':'4'},'future':{'nested':[1.25]},'sessions':[{'id':'s','started_at':'2026-10-01T10:00:00.123Z','ended_at':'2026-10-01T10:40:00.123Z','comment':'','bitrix_record_id':None,'future_session':'x'}]}]
    state=storage.merge_sync_v2(protocol.import_legacy(tasks,'pwa'))
    task=state.tasks[0]
    assert task.daily_priorities['2026-10-01']==2
    assert task.to_dict()['priority']==2
    assert task.to_dict()['created_at']=='2026-10-01T10:00:00.123Z'
    assert task.sessions[0].to_dict()['future_session']=='x'
    assert task.to_dict()['future']=={'nested':[1.25]}


def _parallel_edit(path, field, value, ready, release):
    storage=Storage(Path(path));state=storage.load()
    ready.put(True);release.wait(10)
    setattr(state.tasks[0],field,value);storage.save(state)


def test_two_processes_commit_without_losing_independent_edits(tmp_path):
    import multiprocessing
    storage=prepared(tmp_path)
    ctx=multiprocessing.get_context('fork');ready=ctx.Queue();release=ctx.Event()
    workers=[ctx.Process(target=_parallel_edit,args=(str(storage.path),field,value,ready,release)) for field,value in [('title','Process A'),('description','Process B')]]
    for worker in workers:worker.start()
    try:
        assert ready.get(timeout=10) and ready.get(timeout=10);release.set()
        for worker in workers:worker.join(10);assert worker.exitcode==0
        task=storage.load().tasks[0];assert task.title=='Process A' and task.description=='Process B'
    finally:
        for worker in workers:
            if worker.is_alive():worker.terminate();worker.join()


def test_corrupt_current_restores_valid_backup_and_preserves_corrupt_original(tmp_path):
    storage=prepared(tmp_path);storage.path.write_text('{broken')
    restored=storage.load()
    assert restored.tasks[0].title=='Task' and restored.sync_v2 is not None
    assert any(p.read_text()=='{broken' for p in storage.backup_dir.glob('*corrupt*'))


def test_recovery_rechecks_primary_after_lock_and_keeps_concurrent_repair(tmp_path,monkeypatch):
    from contextlib import contextmanager
    from timerapp_ag.storage_transaction import transaction as real_transaction
    storage=prepared(tmp_path);state=storage.load()
    doc=protocol.change_entity(state.sync_v2,'other',['task','t'],{'title':'Newer repair'})
    repaired=AppState.from_dict({'tasks':protocol.project_tasks(doc)['tasks'],'ui':state.ui,'sync_v2':doc}).to_dict()
    storage.path.write_text('{broken')
    @contextmanager
    def raced_transaction(path):
        with real_transaction(path):
            storage.path.write_text(json.dumps(repaired))
            yield
    monkeypatch.setattr('timerapp_ag.storage.transaction',raced_transaction)
    assert storage.load().tasks[0].title=='Newer repair'


def test_conflict_choice_rejects_unseen_new_candidate(tmp_path):
    storage=prepared(tmp_path);base=storage.load().sync_v2
    left=protocol.change_entity(base,'left',['task','t'],{'title':'Left'})
    right=protocol.change_entity(base,'right',['task','t'],{'title':'Right'})
    state=storage.merge_sync_v2(protocol.merge_documents(left,right))
    shown=next(c for c in protocol.project_document(state.sync_v2)['conflicts'] if c['field']=='title')
    third=protocol.change_entity(base,'third',['task','t'],{'title':'Third'})
    storage.merge_sync_v2(third)
    with pytest.raises(ValueError,match='изменился'):
        storage.resolve_sync_conflict(['task','t'],'title','Left',expected=shown['candidates'])
    current=next(c for c in protocol.project_document(storage.load().sync_v2)['conflicts'] if c['field']=='title')
    assert {c['value'] for c in current['candidates']}=={'Left','Right','Third'}


def test_effective_active_status_is_display_only_not_new_causal_write(tmp_path):
    storage=prepared(tmp_path);base=storage.load().sync_v2
    completed=protocol.change_entity(base,'desktop',['task','t'],{'status':'completed'})
    started=protocol.change_entity(base,'phone',['session','t','new'],{'interval':{'started_at':'2026-01-01T10:00:00Z','ended_at':None},'comment':''})
    state=storage.merge_sync_v2(protocol.merge_documents(completed,started))
    assert state.tasks[0].status==TaskStatus.RUNNING
    assert protocol.project_tasks(state.sync_v2)['tasks'][0]['status']=='completed'
    state.tasks[0].description='unrelated';storage.save(state)
    assert protocol.project_tasks(state.sync_v2)['tasks'][0]['status']=='completed'


def test_invalid_status_is_rejected_even_with_active_session(tmp_path):
    storage=prepared(tmp_path);original=storage.path.read_bytes();base=storage.load().sync_v2
    invalid=protocol.change_entity(base,'phone',['task','t'],{'status':'invalid'})
    invalid=protocol.change_entity(invalid,'phone',['session','t','s'],{'interval':{'started_at':'2026-01-01T10:00:00Z','ended_at':None}})
    with pytest.raises(ValueError,match='статус'):
        storage.merge_sync_v2(invalid)
    assert storage.path.read_bytes()==original
