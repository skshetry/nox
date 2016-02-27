# Copyright 2016 Jon Wayne Parrott
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys

import mock

import nox.main

import contexter
import pytest


RESOURCES = os.path.join(os.path.dirname(__file__), 'resources')


class Namespace(object):
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)


def test_global_config_constructor():
    args = Namespace(
        noxfile='noxfile',
        envdir='dir',
        sessions=['1', '2'],
        reuse_existing_virtualenvs=True,
        stop_on_first_error=False,
        posargs=['a', 'b', 'c'])

    config = nox.main.GlobalConfig(args)

    assert config.noxfile == 'noxfile'
    assert config.envdir == os.path.abspath('dir')
    assert config.sessions == ['1', '2']
    assert config.reuse_existing_virtualenvs is True
    assert config.stop_on_first_error is False
    assert config.posargs == ['a', 'b', 'c']

    args.posargs = ['--', 'a', 'b', 'c']
    config = nox.main.GlobalConfig(args)
    assert config.posargs == ['a', 'b', 'c']


def test_load_user_nox_module():
    noxfile_path = os.path.join(RESOURCES, 'noxfile.py')
    noxfile_module = nox.main.load_user_nox_module(noxfile_path)

    assert noxfile_module.SIGIL == '123'


def test_discover_session_functions():
    def session_1():
        pass

    def session_2():
        pass

    def notasession():
        pass

    mock_module = Namespace(
        session_1=session_1,
        session_2=session_2,
        notasession=notasession)

    session_functions = nox.main.discover_session_functions(mock_module)

    assert session_functions == [
        ('1', session_1),
        ('2', session_2)
    ]


def test_make_sessions():
    def session_1():
        pass

    def session_2():
        pass

    session_functions = [
        ('1', session_1),
        ('2', session_2)
    ]
    global_config = Namespace()
    sessions = nox.main.make_sessions(session_functions, global_config)

    assert sessions[0].name == '1'
    assert sessions[0].func == session_1
    assert sessions[0].global_config == global_config
    assert sessions[1].name == '2'
    assert sessions[1].func == session_2
    assert sessions[1].global_config == global_config


def test_run(monkeypatch):
    global_config = Namespace(
        noxfile='somefile.py',
        sessions=None,
        stop_on_first_error=False)
    user_nox_module = mock.Mock()
    session_functions = mock.Mock()
    sessions = [
        mock.Mock(),
        mock.Mock()
    ]

    with contexter.ExitStack() as stack:
        mock_load_user_module = stack.enter_context(mock.patch(
            'nox.main.load_user_nox_module',
            side_effect=lambda _: user_nox_module))
        mock_discover_session_functions = stack.enter_context(mock.patch(
            'nox.main.discover_session_functions',
            side_effect=lambda _: session_functions))
        mock_make_sessions = stack.enter_context(mock.patch(
            'nox.main.make_sessions', side_effect=lambda _1, _2: sessions))

        # Default options
        nox.main.run(global_config)

        mock_load_user_module.assert_called_with('somefile.py')
        mock_discover_session_functions.assert_called_with(user_nox_module)
        mock_make_sessions.assert_called_with(session_functions, global_config)

        for session in sessions:
            assert session.execute.called
            session.execute.reset_mock()

        # One failing session at the beginning, should still execute all.
        failing_session = mock.Mock()
        failing_session.execute.return_value = False
        sessions.insert(0, failing_session)

        nox.main.run(global_config)

        for session in sessions:
            assert session.execute.called
            session.execute.reset_mock()

        # Now it should stop after the first failed session.
        global_config.stop_on_first_error = True

        nox.main.run(global_config)

        assert sessions[0].execute.called is True
        assert sessions[1].execute.called is False
        assert sessions[2].execute.called is False

        for session in sessions:
            session.reset_mock()

        # This time it should only run a subset of sessions
        sessions[0].execute.return_value = True
        sessions[0].name = '1'
        sessions[1].name = '2'
        sessions[2].name = '3'

        global_config.sessions = ['1', '3']

        nox.main.run(global_config)

        assert sessions[0].execute.called is True
        assert sessions[1].execute.called is False
        assert sessions[2].execute.called is True


def test_main():
    # No args
    sys.argv = [sys.executable]
    with mock.patch('nox.main.run') as run_mock:
        nox.main.main()
        assert run_mock.called
        config = run_mock.call_args[0][0]
        assert config.noxfile == 'nox.py'
        assert config.envdir.endswith('.nox')
        assert config.sessions is None
        assert config.reuse_existing_virtualenvs is False
        assert config.stop_on_first_error is False
        assert config.posargs == []

    # Long-form args
    sys.argv = [
        sys.executable,
        '--noxfile', 'noxfile.py',
        '--envdir', '.other',
        '--sessions', '1', '2',
        '--reuse-existing-virtualenvs',
        '--stop-on-first-error']
    with mock.patch('nox.main.run') as run_mock:
        nox.main.main()
        assert run_mock.called
        config = run_mock.call_args[0][0]
        assert config.noxfile == 'noxfile.py'
        assert config.envdir.endswith('.other')
        assert config.sessions == ['1', '2']
        assert config.reuse_existing_virtualenvs is True
        assert config.stop_on_first_error is True
        assert config.posargs == []

    # Short-form args
    sys.argv = [
        sys.executable,
        '-f', 'noxfile.py',
        '-s', '1', '2',
        '-r']
    with mock.patch('nox.main.run') as run_mock:
        nox.main.main()
        assert run_mock.called
        config = run_mock.call_args[0][0]
        assert config.noxfile == 'noxfile.py'
        assert config.sessions == ['1', '2']
        assert config.reuse_existing_virtualenvs is True

    sys.argv = [
        sys.executable,
        '-e', '1', '2']
    with mock.patch('nox.main.run') as run_mock:
        nox.main.main()
        assert run_mock.called
        config = run_mock.call_args[0][0]
        assert config.sessions == ['1', '2']

    # Posargs
    sys.argv = [
        sys.executable,
        '1', '2', '3']
    with mock.patch('nox.main.run') as run_mock:
        nox.main.main()
        assert run_mock.called
        config = run_mock.call_args[0][0]
        assert config.posargs == ['1', '2', '3']

    sys.argv = [
        sys.executable,
        '--', '1', '2', '3']
    with mock.patch('nox.main.run') as run_mock:
        nox.main.main()
        assert run_mock.called
        config = run_mock.call_args[0][0]
        assert config.posargs == ['1', '2', '3']

    sys.argv = [
        sys.executable,
        '--', '1', '2', '3', '-f', '--baz']
    with mock.patch('nox.main.run') as run_mock:
        nox.main.main()
        assert run_mock.called
        config = run_mock.call_args[0][0]
        assert config.posargs == ['1', '2', '3', '-f', '--baz']