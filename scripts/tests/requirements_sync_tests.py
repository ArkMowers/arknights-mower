"""校验运行时与开发依赖锁文件保持同步。

requirements-dev.in 通过 `-r requirements.txt` 继承运行时锁文件，因此两份锁在
生成的那一刻版本必然一致。但只重新生成其中一份不会有任何报错：运行时装
requirements.txt、CI 的等价性任务装 requirements-dev.txt，一旦漂移，等价性
验证的就不再是实际交付的环境，而测试仍然全绿。这里把这个约束固定下来。

两份锁都必须由 scripts/compile_requirements.py 成对生成。
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNTIME_LOCK = REPO_ROOT / "requirements.txt"
DEVELOPMENT_LOCK = REPO_ROOT / "requirements-dev.txt"

# pip-compile 输出形如 `package==1.2.3` 或 `package[extra]==1.2.3`（--no-strip-extras），
# 行尾可能带 `; python_version < "3.13"` 之类的环境标记。
REQUIREMENT = re.compile(r"^([A-Za-z0-9._-]+)(\[[^\]]*\])?\s*==\s*([^\s;]+)")


def parse_lock(path: Path) -> dict:
    versions = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        matched = REQUIREMENT.match(line.split("#")[0].strip())
        if matched:
            # PyPI 视 `-`、`_`、`.` 与大小写为等价，比较前统一。
            name = re.sub(r"[-_.]+", "-", matched.group(1)).lower()
            versions[name] = matched.group(3)
    return versions


class RequirementsLockSyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = parse_lock(RUNTIME_LOCK)
        cls.development = parse_lock(DEVELOPMENT_LOCK)

    def test_locks_are_not_empty(self):
        # 解析失败会让下面两个断言空转通过，先确认确实读到了内容。
        self.assertGreater(len(self.runtime), 50)
        self.assertGreater(len(self.development), 50)

    def test_development_lock_contains_every_runtime_package(self):
        missing = sorted(set(self.runtime) - set(self.development))
        self.assertEqual(
            missing,
            [],
            msg="requirements-dev.txt 缺少运行时依赖，请运行 "
            "python scripts/compile_requirements.py 重新生成两份锁文件",
        )

    def test_shared_packages_pin_identical_versions(self):
        drifted = {
            name: (self.runtime[name], self.development[name])
            for name in set(self.runtime) & set(self.development)
            if self.runtime[name] != self.development[name]
        }
        self.assertEqual(
            drifted,
            {},
            msg="运行时与开发锁文件版本不一致（包名: 运行时, 开发），等价性测试将"
            "跑在与交付不同的环境上；请运行 python scripts/compile_requirements.py",
        )


if __name__ == "__main__":
    unittest.main()
