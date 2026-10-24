from unittest.mock import Mock

import pytest

from arknights_mower.solvers.mail import MailSolver
from arknights_mower.utils import config
from arknights_mower.utils.config.conf import Conf
from arknights_mower.utils.recognize import Scene


@pytest.mark.parametrize("skip_clear", [False, True])
def test_mail_run_collects_once_and_respects_clear_setting(monkeypatch, skip_clear):
    monkeypatch.setattr(config, "conf", Conf(mail_skip_clear_read=skip_clear))
    solver = MailSolver.__new__(MailSolver)
    solver.recog = Mock()
    solver.check_current_focus = Mock()
    solver.scene = Mock(
        side_effect=[Scene.INDEX, Scene.MAIL, Scene.MATERIEL, Scene.MAIL]
    )
    solver.scene_graph_navigation = Mock()
    solver.tap_element = Mock(return_value=True)
    solver.tap = Mock()
    solver.sleep = Mock()

    solver.run()

    solver.tap_element.assert_called_once_with("read_mail")
    assert solver.scene_graph_navigation.call_count == 2
    solver.scene_graph_navigation.assert_called_with(Scene.MAIL)
    if skip_clear:
        solver.tap.assert_not_called()
        solver.sleep.assert_not_called()
    else:
        solver.tap.assert_called_once_with((1340, 1000))
        solver.sleep.assert_called_once_with(0.25)


def test_old_mail_config_skips_clearing_read_mail_by_default():
    conf = Conf(check_mail_enable=True)
    assert conf.mail_skip_clear_read is True
    assert "mail_skip_clear_read" not in conf.model_dump(exclude_unset=True)


@pytest.mark.parametrize("skip_clear", [False, True])
def test_mail_clear_choice_survives_config_update_and_reload(skip_clear):
    conf = Conf().updated({"mail_skip_clear_read": skip_clear})
    restored = Conf.model_validate_json(conf.model_dump_json(exclude_unset=True))
    assert restored.mail_skip_clear_read is skip_clear
    restored = restored.updated({"check_mail_enable": False})
    assert restored.mail_skip_clear_read is skip_clear
