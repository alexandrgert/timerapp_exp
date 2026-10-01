"""WebDAV v2 replaces legacy richer-wins and unsafe upload-only expectations."""
import json
from unittest.mock import patch
import pytest
from timerapp_ag.storage import AppState, Storage
from timerapp_ag.models import Task
from timerapp_ag import sync_protocol as protocol
from timerapp_ag.webdav_client import WebDavClient, WebDavError
from timerapp_ag.webdav_config import WebDavConfig
from timerapp_ag.webdav_sync import push_local, pull_and_merge, push_local_upload_only, push_merged_state, sync_webdav_now

@pytest.fixture
def webdav_config():
    return WebDavConfig(enabled=True,url='https://example.test/dav/',username='test',password='test',remote_path='tasks.json')

@pytest.fixture
def isolated_metadata():
    with patch('timerapp_ag.webdav_sync.mark_webdav_sync_ok'),patch('timerapp_ag.webdav_sync.mark_webdav_sync_error'),patch('timerapp_ag.webdav_sync.append_entry'):
        yield

class Server:
    def __init__(self, remote=None, legacy=None):
        self.doc=remote;self.legacy=legacy;self.etag='"1"';self.calls=[];self.before_get=None;self.before_put=None;self.reject_put=False
    def request(self, method,url,**kwargs):
        self.calls.append((method,url,kwargs))
        if method=='MKCOL':return 201,b'',{}
        if method=='GET':
            if self.before_get:
                action,self.before_get=self.before_get,None;action()
            if not url.endswith('.v2.json'):
                if self.legacy is None:raise WebDavError('missing',status_code=404)
                return 200,json.dumps(self.legacy).encode(),{'ETag':'"old"'}
            if self.doc is None:raise WebDavError('missing',status_code=404)
            return 200,json.dumps(self.doc).encode(),({'ETag':self.etag} if self.etag else {})
        if method=='PUT':
            if self.before_put:
                action,self.before_put=self.before_put,None;action()
            if self.reject_put:raise WebDavError('offline')
            headers=kwargs['headers']
            if (self.doc is None and headers.get('If-None-Match')!='*') or (self.doc is not None and headers.get('If-Match')!=self.etag):
                raise WebDavError('conflict',status_code=412)
            self.doc=json.loads(kwargs['data']);self.etag='"next"';return 204,b'',{}
        raise AssertionError(method)


def local(tmp_path):
    storage=Storage(tmp_path/'data.json');storage.save(AppState(tasks=[Task(id='local',day='2026-01-01',title='Local')]))
    return storage


def test_remote_legacy_import_once_without_writing_old_file(tmp_path,webdav_config,isolated_metadata):
    storage=local(tmp_path)
    server=Server(legacy={'tasks':[{'id':'remote','day':'2026-01-01','title':'Remote','sessions':[]}]})
    with patch.object(WebDavClient,'_request',side_effect=server.request):
        outcome=push_local(storage,webdav_config)
        assert {t.id for t in outcome.state.tasks}=={'local','remote'}
        assert all(url.endswith('.v2.json') for method,url,_ in server.calls if method=='PUT')
        assert list(storage.backup_dir.glob('*remote-legacy*'))
        state=storage.load();state.tasks=[t for t in state.tasks if t.id!='remote'];storage.save(state)
        server.doc=None
        push_local(storage,webdav_config)
        assert {t.id for t in storage.load().tasks}=={'local'}


@pytest.mark.parametrize('entry',[push_local,push_local_upload_only,push_merged_state])
def test_all_write_paths_merge_and_use_conditional_put(tmp_path,webdav_config,isolated_metadata,entry):
    storage=local(tmp_path)
    remote=protocol.import_legacy([{'id':'remote','day':'2026-01-01','title':'R','sessions':[]}],'phone')
    server=Server(remote)
    with patch.object(WebDavClient,'_request',side_effect=server.request):
        outcome=entry(storage,webdav_config)
    assert {t.id for t in outcome.state.tasks}=={'local','remote'}
    put=[c for c in server.calls if c[0]=='PUT']
    assert len(put)==1 and put[0][2]['headers']['If-Match']=='"1"'
    assert not any('sync-meta' in c[1] for c in server.calls)


def test_412_refetch_preserves_remote_edit_and_local_edit_during_get(tmp_path,webdav_config,isolated_metadata):
    storage=local(tmp_path);state=storage.enable_sync_v2();server=Server(state.sync_v2)
    def edit_local():
        current=storage.load();current.tasks[0].title='Locally edited';storage.save(current)
    def edit_remote():
        server.doc=protocol.change_entity(server.doc,'phone',['task','local'],{'description':'Remote edit'});server.etag='"2"'
    server.before_get=edit_local;server.before_put=edit_remote
    with patch.object(WebDavClient,'_request',side_effect=server.request):
        outcome=push_local(storage,webdav_config)
    assert outcome.state.tasks[0].title=='Locally edited'
    assert outcome.state.tasks[0].description=='Remote edit'
    assert len([c for c in server.calls if c[0]=='PUT'])==2


def test_local_edit_during_put_remains_on_disk_and_next_sync_sends_it(tmp_path,webdav_config,isolated_metadata):
    storage=local(tmp_path);server=Server(storage.enable_sync_v2().sync_v2)
    def edit():
        current=storage.load();current.tasks[0].title='During PUT';storage.save(current)
    server.before_put=edit
    with patch.object(WebDavClient,'_request',side_effect=server.request):
        result=push_local(storage,webdav_config)
        assert result.state.tasks[0].title=='During PUT'
        push_local(storage,webdav_config)
    assert protocol.project_tasks(server.doc)['tasks'][0]['title']=='During PUT'


@pytest.mark.parametrize('etag',[None,'W/"weak"','bare'])
def test_missing_or_weak_etag_never_writes(tmp_path,webdav_config,isolated_metadata,etag):
    storage=local(tmp_path);server=Server(storage.enable_sync_v2().sync_v2);server.etag=etag
    with patch.object(WebDavClient,'_request',side_effect=server.request),pytest.raises(WebDavError,match='ETag'):
        push_local(storage,webdav_config)
    assert not any(c[0]=='PUT' for c in server.calls)


def test_pull_is_read_only_and_empty_remote_creation_is_conditional(tmp_path,webdav_config,isolated_metadata):
    storage=local(tmp_path);server=Server()
    with patch.object(WebDavClient,'_request',side_effect=server.request):
        pull_and_merge(storage,webdav_config)
        assert not any(c[0]=='PUT' for c in server.calls)
        push_local(storage,webdav_config)
    put=next(c for c in server.calls if c[0]=='PUT');assert put[2]['headers']['If-None-Match']=='*'


def test_errors_keep_local_data_and_disabled_or_unconfigured_never_connect(tmp_path,webdav_config,isolated_metadata):
    storage=local(tmp_path);server=Server(storage.enable_sync_v2().sync_v2);server.reject_put=True
    with patch.object(WebDavClient,'_request',side_effect=server.request):
        outcome=sync_webdav_now(storage,webdav_config)
    assert outcome.error and storage.load().tasks[0].title=='Local'
    webdav_config.enabled=False
    with patch.object(WebDavClient,'_request') as request,pytest.raises(WebDavError,match='отключена'):
        push_local(storage,webdav_config)
    request.assert_not_called()
    with patch.object(WebDavClient,'_request') as request:
        outcome=sync_webdav_now(storage,WebDavConfig())
    assert outcome.error;request.assert_not_called()


def test_shutdown_pending_notice_and_reconnect_use_same_safe_path(tmp_path,webdav_config,isolated_metadata):
    from timerapp_ag.webdav_sync import sync_webdav_on_shutdown,sync_webdav_on_reconnect
    storage=local(tmp_path);base=storage.enable_sync_v2().sync_v2
    current=storage.load();current.tasks[0].title='Desktop';storage.save(current)
    server=Server(protocol.change_entity(base,'phone',['task','local'],{'title':'Phone'}))
    webdav_config.sync_on_shutdown=True;webdav_config.shutdown_upload_only=True
    with patch('timerapp_ag.webdav_sync.load_webdav_config',return_value=webdav_config),patch('timerapp_ag.webdav_sync.save_webdav_pending_notice') as notice,patch.object(WebDavClient,'_request',side_effect=server.request):
        result=sync_webdav_on_shutdown(storage)
        assert result.conflict_detected;notice.assert_called_once()
        assert not sync_webdav_on_reconnect(storage).error
    assert all('If-Match' in c[2]['headers'] for c in server.calls if c[0]=='PUT')


def test_exists_keeps_head_fallback_and_404_semantics(webdav_config):
    client=WebDavClient(webdav_config)
    with patch.object(client,'_request',side_effect=WebDavError('missing',status_code=404)):
        assert not client.exists()
    with patch.object(client,'_request',side_effect=[WebDavError('unsupported',status_code=405),(206,b'x',{})]) as request:
        assert client.exists();assert [c.args[0] for c in request.call_args_list]==['HEAD','GET']


def test_https_required_before_any_credentials_sent(webdav_config):
    client=WebDavClient(webdav_config)
    with patch('urllib.request.build_opener') as opener,pytest.raises(WebDavError,match='HTTPS'):
        client.download('http://example.test/data')
    opener.assert_not_called()


@pytest.mark.parametrize('extra',[{'version':3},{'sync_v2':{}},{'_sync_v2':{}},{'schemaVersion':2}])
def test_future_legacy_envelope_is_not_imported_or_uploaded(tmp_path,webdav_config,isolated_metadata,extra):
    storage=local(tmp_path);server=Server(legacy={'tasks':[],**extra})
    with patch.object(WebDavClient,'_request',side_effect=server.request),pytest.raises(WebDavError,match='Неподдерживаемый'):
        push_local(storage,webdav_config)
    assert not any(c[0]=='PUT' for c in server.calls)
    assert storage.load().tasks[0].title=='Local'
