"""Verify that relaunching cannot target Python workers from another project."""
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

import run_integrated as launcher


class LauncherTests(unittest.TestCase):
    def info(self, **changes):
        data = dict(pid=os.getpid()+10000, name='python.exe',
                    cmdline=['python.exe', 'dashboard.py'], cwd=str(launcher.ROOT))
        data.update(changes)
        return data

    def test_matches_relative_script_only_with_correct_working_directory(self):
        self.assertTrue(launcher.is_project_worker(self.info()))
        self.assertFalse(launcher.is_project_worker(self.info(cwd=str(launcher.ROOT / '別폴더'))))
        self.assertFalse(launcher.is_project_worker(self.info(cwd=None)))

    def test_absolute_script_is_matched_and_other_versions_left_running(self):
        self.assertTrue(launcher.is_project_worker(self.info(cmdline=['python.exe', str(launcher.ROOT/'dashboard.py')], cwd=None)))
        for script in (launcher.ROOT/'추가개발'/'app.py', launcher.ROOT/'kbond_v3'/'app.py', launcher.ROOT/'other.py'):
            self.assertFalse(launcher.is_project_worker(self.info(cmdline=['python.exe', str(script)])))

    def test_never_targets_messenger_self_or_python_command(self):
        self.assertFalse(launcher.is_project_worker(self.info(name='KBondMessenger.exe')))
        self.assertFalse(launcher.is_project_worker(self.info(pid=os.getpid())))
        self.assertFalse(launcher.is_project_worker(self.info(pid=os.getppid())))
        self.assertFalse(launcher.is_project_worker(self.info(cmdline=['python.exe','-c','dashboard.py'])))
        self.assertFalse(launcher.is_project_worker(self.info(cmdline=['python.exe','-m','dashboard.py'])))

    def test_readiness_requires_exact_new_instance_and_revision(self):
        process = Mock()
        process.poll.return_value = None
        health = Mock(side_effect=[{'app':'kbond-integrated','instance':'old','revision':'v1','watchlist':True},
                                   {'app':'kbond-integrated','instance':'new','revision':'v1','watchlist':True},
                                   {'app':'kbond-integrated','instance':'new','revision':'v2','watchlist':True}])
        with patch.object(launcher.time, 'sleep'):
            launcher.wait_ready(process, 'new', 'v2', health=health)
        self.assertEqual(health.call_count, 3)

    def test_failed_start_never_opens_an_old_server(self):
        process = Mock()
        process.poll.return_value = 1
        health = Mock()
        with self.assertRaises(RuntimeError):
            launcher.wait_ready(process, 'new', 'v2', health=health)
        health.assert_not_called()

    def test_only_project_workers_are_terminated(self):
        own = Mock(info=self.info(), pid=100)
        other = Mock(info=self.info(cwd=str(launcher.ROOT/'other')), pid=200)
        backend = Mock()
        backend.process_iter.return_value = [own, other]
        backend.wait_procs.return_value = ([own], [])
        backend.Error = OSError
        backend.NoSuchProcess = ProcessLookupError
        backend.ancestor_pids.return_value = {os.getpid(), os.getppid()}
        launcher.stop_previous(backend)
        own.terminate.assert_called_once()
        other.terminate.assert_not_called()

    def test_never_stops_matching_venv_redirector_ancestors(self):
        ancestor = Mock(info=self.info(pid=32100), pid=32100)
        old = Mock(info=self.info(pid=32200), pid=32200)
        backend = Mock()
        backend.process_iter.return_value = [ancestor, old]
        backend.wait_procs.return_value = ([old], [])
        backend.Error = OSError
        backend.NoSuchProcess = ProcessLookupError
        backend.ancestor_pids.return_value = {os.getpid(), os.getppid(), 32100}
        launcher.stop_previous(backend)
        ancestor.terminate.assert_not_called()
        old.terminate.assert_called_once()

    @unittest.skipUnless(os.name == 'nt', 'Windows venv redirector')
    def test_venv_script_launch_survives_parent_protection(self):
        result = subprocess.run([sys.executable, str(launcher.ROOT/'run_integrated.py'), '--self-check'],
                                cwd=launcher.ROOT, capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('PASS: current interpreter and venv parent are protected', result.stdout)

    def test_bat_uses_verified_launcher_and_no_longer_spawns_unmanaged_dashboard(self):
        batch = (launcher.ROOT/'K-Bond_통합실행.bat').read_text(encoding='utf-8')
        self.assertIn('run_integrated.py', batch)
        self.assertNotIn('start "K-Bond Dashboard"', batch)
        self.assertNotIn('timeout /t 2', batch)

    def test_dashboard_identifies_current_build_and_bypasses_cache(self):
        import dashboard
        client = dashboard.app.test_client()
        with patch.dict(os.environ, {'KBOND_INSTANCE_TOKEN':'test-instance'}):
            response = client.get('/api/health')
            data = response.get_json()
            self.assertEqual(data['app'], 'kbond-integrated')
            self.assertTrue(data['watchlist'])
            self.assertEqual(data['instance'], 'test-instance')
            self.assertEqual(data['revision'], launcher.source_revision())
        page = client.get('/')
        self.assertIn(b'id="watchTab"', page.data)
        self.assertIn('관심조건 지원'.encode(), page.data)
        self.assertEqual(page.headers['Cache-Control'], 'no-store')

    @unittest.skipUnless(os.name == 'nt', 'Windows native process inspection')
    def test_windows_backend_reads_current_command_and_working_directory(self):
        import windows_processes
        native = windows_processes.api()
        handle = native.open(os.getpid(), 0x1000)
        try:
            command = native.command(handle)
            self.assertTrue(command)
            self.assertGreater(native.creation(handle), 0)
            self.assertEqual(Path(native.cwd(os.getpid())).resolve(), Path.cwd().resolve())
        finally:
            native.kernel.CloseHandle(handle)

    @unittest.skipUnless(os.name == 'nt', 'Windows native process inspection')
    def test_windows_backend_finds_and_stops_only_its_test_child(self):
        import windows_processes
        child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(20)'], cwd=launcher.ROOT)
        try:
            found = next((p for p in windows_processes.process_iter([]) if p.pid == child.pid), None)
            self.assertIsNotNone(found)
            self.assertEqual(Path(found.info['cwd']).resolve(), launcher.ROOT)
            # It is a Python -c process and must never be treated as a project worker.
            self.assertFalse(launcher.is_project_worker(found.info))
            found.terminate()
            child.wait(timeout=3)
            self.assertFalse(found.alive())
        finally:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=3)


if __name__ == '__main__':
    unittest.main()
