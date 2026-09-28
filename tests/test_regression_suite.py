"""The suite rejects model changes and separates completion from quality gates."""
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock,patch
from tools import regression_suite as suite


class RegressionSuiteTests(unittest.TestCase):
    manifest={'weights_sha256':'fixed','question_heads':{'item':{'weights_sha256':'item-fixed'}}}

    def launch(self,root):
        count=0
        def start(command,*,cwd,stdout,stderr):
            nonlocal count
            count+=1;run=root/'runs'/('recording'+str(count));run.mkdir()
            stdout.write('RUN '+str(run)+'\n');stdout.flush()
            (run/'verification.json').write_text(json.dumps(dict(experiment_valid=True,level_completed=True,passed=False,authority={'pass':True})))
            (run/'summary.json').write_text(json.dumps(dict(status='completed',levels_completed=1)))
            (run/'decisions.jsonl').write_text(json.dumps({'routing':self.manifest})+'\n')
            return Mock(pid=123,wait=Mock(return_value=0))
        return start

    def test_completion_is_distinct_from_quality_and_unicode_paths_work(self):
        with tempfile.TemporaryDirectory(prefix='José_Иван_') as tmp:
            root=Path(tmp);(root/'runs').mkdir();read=Path.read_text
            def locale_read(path,*args,**kwargs):
                if path.suffix=='.log' and not args and kwargs.get('encoding') is None:kwargs['encoding']='cp1251'
                return read(path,*args,**kwargs)
            with patch.object(suite,'ROOT',root),patch.object(suite,'CASES',(('MAP01',48,180),)),patch.object(suite,'identity',return_value=self.manifest),patch.object(suite.sys,'argv',['suite']),patch.object(suite.subprocess,'Popen',side_effect=self.launch(root)),patch.object(suite.subprocess,'run',return_value=Mock(returncode=1)),patch.object(Path,'read_text',locale_read),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(suite.main(),0)
            report=json.loads(next((root/'runs').glob('*_suite/suite.json')).read_text())
            self.assertTrue(report['passed'])
            self.assertFalse(report['results'][0]['verification']['passed'])
            flags=report['common_flags']
            self.assertEqual(flags[flags.index('--minimum-decision-delay-ticks')+1],'0')

    def test_failed_completion_stops_after_the_full_first_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'runs').mkdir();start=self.launch(root)
            def failed(command,**kwargs):
                child=start(command,**kwargs)
                path=root/'runs'/'recording1'/'verification.json'
                report=json.loads(path.read_text());report['level_completed']=False
                path.write_text(json.dumps(report));return child
            with patch.object(suite,'ROOT',root),patch.object(suite,'CASES',(('MAP01',48,180),('MAP02',54,1800))),patch.object(suite,'identity',return_value=self.manifest),patch.object(suite.sys,'argv',['suite']),patch.object(suite.subprocess,'Popen',side_effect=failed) as launch,patch.object(suite.subprocess,'run',return_value=Mock(returncode=1)),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(suite.main(),1)
                self.assertEqual(launch.call_count,1)
            report=json.loads(next((root/'runs').glob('*_suite/suite.json')).read_text())
            self.assertEqual(report['status'],'stopped_after_failure')
            self.assertFalse(report['passed'])

    def test_model_change_stops_before_the_next_game(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'runs').mkdir();changed=dict(self.manifest,weights_sha256='different')
            with patch.object(suite,'ROOT',root),patch.object(suite,'CASES',(('MAP01',48,180),('MAP02',54,1800))),patch.object(suite,'identity',side_effect=[self.manifest,self.manifest,self.manifest,changed]),patch.object(suite.sys,'argv',['suite']),patch.object(suite.subprocess,'Popen',side_effect=self.launch(root)) as launch,patch.object(suite.subprocess,'run',return_value=Mock(returncode=1)),contextlib.redirect_stdout(io.StringIO()):
                with self.assertRaisesRegex(ValueError,'Model changed before MAP02'):suite.main()
                self.assertEqual(launch.call_count,1)
            report=json.loads(next((root/'runs').glob('*_suite/suite.json')).read_text())
            self.assertEqual(report['status'],'failed')
            self.assertEqual(len(report['results']),1)

    def test_first_map_reorders_but_keeps_all_required_cases(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'runs').mkdir()
            with patch.object(suite,'ROOT',root),patch.object(suite,'identity',return_value=self.manifest),patch.object(suite.sys,'argv',['suite','--first-map','MAP03','--enemy-events','--minimum-decision-delay-ticks','16']),patch.object(suite.subprocess,'Popen',side_effect=self.launch(root)) as launch,patch.object(suite.subprocess,'run',return_value=Mock(returncode=1)),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(suite.main(),0)
            commands=[call.args[0] for call in launch.call_args_list]
            self.assertEqual([command[command.index('--map')+1] for command in commands],['MAP03','MAP01','MAP02'])
            self.assertTrue(all('--enemy-events' in command for command in commands))
            self.assertTrue(all(command[command.index('--minimum-decision-delay-ticks')+1]=='16' for command in commands))
            self.assertEqual(suite.FLAGS[suite.FLAGS.index('--minimum-decision-delay-ticks')+1],'0')
            report=json.loads(next((root/'runs').glob('*_suite/suite.json')).read_text())
            self.assertEqual({(case['map'],case['seed'],case['seconds']) for case in report['cases']},set(suite.CASES))
            self.assertIn('--enemy-events',report['common_flags'])


if __name__=='__main__':unittest.main()
