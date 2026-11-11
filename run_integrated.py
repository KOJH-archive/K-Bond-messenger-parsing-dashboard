"""Restart only this project's Python workers, then open the verified new dashboard."""
import hashlib
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request
import uuid
import webbrowser

ROOT = Path(__file__).resolve().parent
URL = 'http://127.0.0.1:5000'
WORKERS = {'dashboard.py', 'kbond_scraper.py', 'desktop_alert.py', 'run_integrated.py'}


def source_revision():
    digest = hashlib.sha256()
    for name in ('dashboard.py', 'watch_api.py', 'watch_service.py', 'watch_filters.py',
                 'desktop_alert.py', 'templates/index.html', 'static/watch.js', 'static/watch.css'):
        digest.update(name.encode())
        digest.update((ROOT / name).read_bytes())
    return digest.hexdigest()


def is_project_worker(info, root=ROOT, protected=()):
    """Resolve relative scripts against their actual working directory, not their filename alone."""
    if info.get('pid') in {os.getpid(), os.getppid(), *protected}:
        return False
    name = str(info.get('name') or '').casefold()
    if not (name.startswith('python') and name.endswith('.exe')):
        return False
    command = info.get('cmdline') or []
    # Python -c/-m instructions are not script launches even if their arguments mention a .py file.
    if any(flag in command[1:] for flag in ('-c', '-m')):
        return False
    for argument in command[1:]:
        script = Path(argument)
        if script.name.casefold() not in WORKERS:
            continue
        if not script.is_absolute():
            if not info.get('cwd'):
                continue
            script = Path(info['cwd']) / script
        if script.resolve().parent == root.resolve():
            return True
    return False


def stop_previous(psutil):
    # A Windows venv may have both a redirector and interpreter with the SAME argv.
    # Killing the redirector parent also ends the current launch; protect the entire ancestry.
    protected = psutil.ancestor_pids(os.getpid())
    logging.info('Launcher ancestry protected: %s', sorted(protected))
    workers = []
    for process in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
        try:
            if is_project_worker(process.info, protected=protected):
                workers.append(process)
        except (OSError, psutil.Error):
            continue
    # Stop the prior supervisor before its children so it cannot race the new launch.
    workers.sort(key=lambda p: not any(Path(arg).name == 'run_integrated.py' for arg in (p.info.get('cmdline') or [])))
    for process in workers:
        try:
            print(f"이 폴더의 이전 실행 종료: PID {process.pid}", flush=True)
            logging.info('Stopping old project worker PID %s', process.pid)
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _gone, alive = psutil.wait_procs(workers, timeout=5)
    if alive:
        raise RuntimeError('이전 K-Bond 실행을 종료하지 못했습니다. 해당 실행 창을 닫고 다시 실행해 주세요.')


def read_health():
    # Local readiness checks must not pass through a system HTTP proxy.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(URL + '/api/health', timeout=1) as response:
        return json.load(response)


def wait_ready(process, token, revision, timeout=12, health=read_health):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError('대시보드 시작에 실패했습니다. data/dashboard-runtime.log를 확인해 주세요.')
        try:
            data = health()
            if (data.get('app') == 'kbond-integrated' and data.get('instance') == token
                    and data.get('revision') == revision and data.get('watchlist') is True):
                return
        except (OSError, ValueError):
            pass
        time.sleep(.2)
    raise RuntimeError('새 대시보드 응답을 확인하지 못했습니다. 5000번 포트 또는 실행 권한을 확인해 주세요.')


def stop_child(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=2)


def main():
    import windows_processes as psutil
    dashboard = collector = None
    try:
        (ROOT / 'data').mkdir(exist_ok=True)
        logging.basicConfig(filename=ROOT/'data'/'launcher-runtime.log', encoding='utf-8',
                            level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
        logging.info('Starting integrated launcher PID %s; parent %s', os.getpid(), os.getppid())
        stop_previous(psutil)
        revision = source_revision()
        token = uuid.uuid4().hex
        environment = os.environ.copy()
        environment['KBOND_INSTANCE_TOKEN'] = token
        environment['PYTHONIOENCODING'] = 'utf-8'
        (ROOT / 'data').mkdir(exist_ok=True)
        with (ROOT / 'data' / 'dashboard-runtime.log').open('w', encoding='utf-8') as logfile:
            dashboard = subprocess.Popen([sys.executable, str(ROOT / 'dashboard.py')], cwd=ROOT,
                                         env=environment, stdout=logfile, stderr=logfile,
                                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            wait_ready(dashboard, token, revision)
            collector = subprocess.Popen([sys.executable, str(ROOT / 'kbond_scraper.py')], cwd=ROOT,
                                         env=environment)
            print(f'최신 통합 대시보드 확인 완료 · 관심조건 탭 포함 · 버전 {revision[:10]}')
            print('종료하려면 이 창에서 Ctrl+C를 누르세요.')
            webbrowser.open(URL + '/?v=' + revision[:10])
            while dashboard.poll() is None and collector.poll() is None:
                time.sleep(.5)
            if collector.poll() is not None:
                raise RuntimeError('수집기가 종료되었습니다. 위의 오류 내용을 확인해 주세요.')
            raise RuntimeError('대시보드가 종료되었습니다. data/dashboard-runtime.log를 확인해 주세요.')
    except KeyboardInterrupt:
        print('K-Bond 대시보드와 수집기를 종료합니다.')
        return 0
    except Exception as exc:
        logging.exception('Integrated launch failed')
        print('[실행 오류] ' + str(exc), flush=True)
        print('자세한 기록: data/launcher-runtime.log', flush=True)
        return 1
    finally:
        stop_child(collector)
        stop_child(dashboard)


if __name__ == '__main__':
    if '--self-check' in sys.argv:
        import windows_processes
        protected = windows_processes.ancestor_pids(os.getpid())
        parent = next((p for p in windows_processes.process_iter([]) if p.pid == os.getppid()), None)
        # This mode never stops workers or starts a server. It tests the real venv redirector chain.
        assert os.getpid() in protected and os.getppid() in protected
        assert not is_project_worker({'pid':os.getpid()})
        if parent:
            assert not is_project_worker(parent.info, protected=protected)
        same_script_parent = bool(parent and any(Path(arg).name == 'run_integrated.py'
                                                for arg in parent.info.get('cmdline', [])))
        print('PASS: current interpreter and venv parent are protected; no processes stopped.')
        print('Matching parent Python wrapper detected:', same_script_parent)
    else:
        raise SystemExit(main())
