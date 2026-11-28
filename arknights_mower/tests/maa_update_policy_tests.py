import unittest

from arknights_mower.utils.config.conf import Conf


class MaaUpdatePolicyTests(unittest.TestCase):
    def test_defaults_do_not_install_updates(self):
        conf = Conf()
        self.assertFalse(conf.maa_auto_update)
        self.assertFalse(conf.maa_resource_auto_update)
        self.assertFalse(conf.maa_resource_auto_check_update)
        saved = conf.model_dump(exclude_unset=True)
        for key in (
            "maa_auto_check_update",
            "maa_auto_update",
            "maa_resource_auto_check_update",
            "maa_resource_auto_update",
        ):
            self.assertNotIn(key, saved)

    def test_legacy_combined_check_migrates_without_enabling_install(self):
        conf = Conf(maa_auto_check_update=True)
        self.assertTrue(conf.maa_auto_check_update)
        self.assertTrue(conf.maa_resource_auto_check_update)
        self.assertFalse(conf.maa_auto_update)
        self.assertFalse(conf.maa_resource_auto_update)

    def test_explicit_resource_policy_is_independent_and_survives_reload(self):
        conf = Conf(maa_auto_check_update=True, maa_resource_auto_check_update=False)
        restored = Conf(**conf.updated({"theme": "dark"}).model_dump())
        self.assertTrue(restored.maa_auto_check_update)
        self.assertFalse(restored.maa_resource_auto_check_update)

    def test_install_only_enables_its_own_component_check(self):
        for field, check, other in (
            (
                "maa_auto_update",
                "maa_auto_check_update",
                "maa_resource_auto_check_update",
            ),
            (
                "maa_resource_auto_update",
                "maa_resource_auto_check_update",
                "maa_auto_check_update",
            ),
        ):
            with self.subTest(field=field):
                conf = Conf(**{field: True})
                self.assertTrue(getattr(conf, check))
                self.assertFalse(getattr(conf, other))
