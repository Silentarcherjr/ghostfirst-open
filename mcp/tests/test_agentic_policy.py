"""The research driver must obey the same fail-closed async contract."""
import importlib.util
from pathlib import Path
import pytest

DRIVER = Path(__file__).resolve().parents[3]/'research/agentic_trace/run_trace.py'
if not DRIVER.is_file():
    # The research driver lives only in the private monorepo, not the public subtree.
    pytest.skip('research driver not present', allow_module_level=True)
spec = importlib.util.spec_from_file_location('trace_driver', DRIVER)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)

@pytest.mark.parametrize('status,changed,recommended,expected', [
    ('checking',True,'deep_check','stop'),
    ('error',True,'deep_check','stop'),
    ('declined_by_human',True,'deep_check','stop'),
    ('checked',False,'deep_check','stop'),
    ('checked',True,None,'stop'),
    ('checked',True,'deep_check','deep_check'),
])
def test_only_completed_consistent_evidence_can_escalate(status,changed,recommended,expected):
    assert driver.decide(dict(status=status,page_changed_after_load=changed,recommended_next_step=recommended)) == expected


def test_driver_polls_same_job_until_final_result(monkeypatch):
    agent=object.__new__(driver.Agent)
    calls=[]
    answers=iter([{'status':'checking','job_id':'opaque'}, {'status':'checking','job_id':'opaque'}, {'status':'error','error_code':'request_timeout'}])
    def request(method, params):
        calls.append(params)
        return {'structuredContent':next(answers)}
    agent.request=request
    monkeypatch.setattr(driver.time,'sleep',lambda _:None)
    result=agent.tool('check_link','https://example.com/')
    assert result['status']=='error'
    assert [call['name'] for call in calls] == ['check_link','get_check_result','get_check_result']
    assert all(call['arguments']=={'job_id':'opaque'} for call in calls[1:])
