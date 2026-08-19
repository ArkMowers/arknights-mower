"""Static contract tests for the shared release workflows."""

import unittest
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
BUILD_WORKFLOW_PATH = REPO_ROOT / ".github/workflows/release-build.yml"
PREPARE_WORKFLOW_PATH = REPO_ROOT / ".github/workflows/prepare-release.yml"
VERSION = "${{ needs.prepare.outputs.version }}"
TAG_NAME = "${{ needs.prepare.outputs.tag_name }}"


def load_workflow(path: Path) -> dict:
    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
    # PyYAML follows YAML 1.1 and parses the unquoted key `on` as True.
    workflow["on"] = workflow.pop(True, workflow.get("on"))
    return workflow


def find_step(job: dict, name: str) -> dict:
    return next(step for step in job["steps"] if step.get("name") == name)


def all_run_commands(workflow: dict) -> str:
    return "\n".join(
        step.get("run", "")
        for job in workflow["jobs"].values()
        for step in job.get("steps", [])
    )


class CrossPlatformReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = load_workflow(BUILD_WORKFLOW_PATH)
        cls.jobs = cls.workflow["jobs"]

    def test_workflow_name_covers_release_types(self):
        self.assertEqual(self.workflow["name"], "Release & Prerelease")

    def test_stable_alpha_tag_and_reusable_triggers(self):
        triggers = self.workflow["on"]
        self.assertEqual(
            triggers["push"],
            {
                "tags": [
                    "v[0-9]+.[0-9]+.[0-9]+",
                    "v[0-9]+.[0-9]+.[0-9]+-alpha.[0-9]+",
                ]
            },
        )
        self.assertEqual(
            triggers["workflow_call"]["inputs"]["tag_name"],
            {
                "description": "已由发布准备流程创建的合法发布 tag",
                "type": "string",
                "required": True,
            },
        )
        self.assertEqual(
            triggers["workflow_call"]["inputs"]["release_sha"],
            {
                "description": "发布 tag 必须指向的提交",
                "type": "string",
                "required": True,
            },
        )
        self.assertNotIn("workflow_dispatch", triggers)

    def test_permissions_are_minimal(self):
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertEqual(self.jobs["release"]["permissions"], {"contents": "write"})
        self.assertNotIn("actions", self.workflow["permissions"])
        self.assertNotIn("actions", self.jobs["release"]["permissions"])

    def test_all_build_jobs_exist_once(self):
        self.assertEqual(
            set(self.jobs),
            {"prepare", "build-windows", "build-linux", "build-macos", "release"},
        )

    def test_release_waits_for_all_builds(self):
        release = self.jobs["release"]
        self.assertNotIn("if", release)
        self.assertEqual(
            set(release["needs"]),
            {"prepare", "build-windows", "build-linux", "build-macos"},
        )

    def test_version_is_validated_and_controls_release_type(self):
        prepare = self.jobs["prepare"]
        self.assertEqual(
            prepare["outputs"],
            {
                "version": "${{ steps.meta.outputs.version }}",
                "tag_name": "${{ steps.meta.outputs.tag_name }}",
                "prerelease": "${{ steps.meta.outputs.prerelease }}",
            },
        )
        resolve = find_step(prepare, "Resolve version")["run"]
        self.assertIn(r"^v[0-9]+\.[0-9]+\.[0-9]+(-alpha\.[0-9]+)?$", resolve)
        self.assertIn('git show-ref --verify --quiet "refs/tags/${tag_name}"', resolve)
        self.assertIn('"refs/tags/${tag_name}^{commit}"', resolve)
        self.assertIn('"${tag_sha}" != "${expected_sha}"', resolve)
        self.assertIn('if [[ "${version}" == *-alpha.* ]]', resolve)

        publish = find_step(self.jobs["release"], "Publish GitHub Release")
        self.assertFalse(publish["with"]["draft"])
        self.assertEqual(publish["with"]["tag_name"], TAG_NAME)
        self.assertEqual(
            publish["with"]["prerelease"],
            "${{ needs.prepare.outputs.prerelease == 'true' }}",
        )

    def test_reusable_call_prefers_explicit_inputs_over_inherited_event_context(self):
        resolve = find_step(self.jobs["prepare"], "Resolve version")["run"]
        self.assertIn('if [[ -n "${CALLED_TAG_NAME}" ]]; then', resolve)
        self.assertNotIn("GITHUB_EVENT_NAME", resolve)

    def test_every_job_checks_out_the_resolved_tag(self):
        prepare_checkout = find_step(self.jobs["prepare"], "Checkout repository")
        self.assertEqual(
            prepare_checkout["with"]["ref"],
            "${{ inputs.tag_name || github.ref_name }}",
        )
        for job_name in ("build-windows", "build-linux", "build-macos"):
            checkout = find_step(self.jobs[job_name], "Checkout repository")
            self.assertEqual(checkout["with"]["ref"], TAG_NAME)

    def test_runner_labels(self):
        self.assertEqual(self.jobs["build-windows"]["runs-on"], "windows-latest")
        self.assertEqual(
            self.jobs["build-linux"]["strategy"]["matrix"]["include"],
            [
                {"runner": "ubuntu-24.04", "arch": "x64"},
                {"runner": "ubuntu-24.04-arm", "arch": "arm64"},
            ],
        )
        self.assertEqual(
            self.jobs["build-macos"]["strategy"]["matrix"]["include"],
            [
                {"runner": "macos-15-intel", "arch": "x64", "macho": "x86_64"},
                {"runner": "macos-15", "arch": "arm64", "macho": "arm64"},
            ],
        )

    def test_artifact_names_match_release_paths(self):
        expected = {
            "build-windows": f"arknights-mower_{VERSION}_windows_x64",
            "build-linux": f"arknights-mower_{VERSION}_linux_${{{{ matrix.arch }}}}",
            "build-macos": f"arknights-mower_{VERSION}_macos_${{{{ matrix.arch }}}}",
        }
        for job_name, artifact in expected.items():
            upload = find_step(self.jobs[job_name], "Upload artifact")
            self.assertEqual(
                upload["with"]["name"], artifact, msg=f"{job_name} upload name"
            )
            self.assertIn(
                artifact, upload["with"]["path"], msg=f"{job_name} upload path"
            )

        release_download = find_step(self.jobs["release"], "Download build artifacts")
        self.assertEqual(
            release_download["with"],
            {
                "path": "release-assets",
                "pattern": "arknights-mower_*",
                "merge-multiple": True,
            },
        )

        publish = find_step(self.jobs["release"], "Publish GitHub Release")
        self.assertIn("release-assets/arknights-mower_*", publish["with"]["files"])
        self.assertIn("release-assets/SHA256SUMS", publish["with"]["files"])

    def test_sha256_manifest_step(self):
        manifest = find_step(self.jobs["release"], "Generate SHA-256 manifest")
        self.assertIn("sha256sum", manifest["run"])
        self.assertIn("SHA256SUMS", manifest["run"])

    def test_prepare_appends_unsigned_notes_without_download_list(self):
        append = find_step(self.jobs["prepare"], "Append signing notes to body")
        run = append["run"]
        self.assertNotIn("## 下载", run)
        self.assertNotIn("arknights-mower_", run)
        self.assertIn("SHA256SUMS", run)
        self.assertIn("SmartScreen", run)
        self.assertIn("unsigned experimental", run)

    def test_builds_share_version_injection(self):
        command = f'python scripts/inject_version.py "{VERSION}"'
        for job_name in ("build-windows", "build-linux", "build-macos"):
            step = find_step(self.jobs[job_name], "Inject version from tag")
            self.assertEqual(step["run"], command, msg=f"{job_name} inject step")

    def test_windows_build_verifies_pe_arch_before_packaging(self):
        job = self.jobs["build-windows"]
        names = [step.get("name") for step in job["steps"]]
        build_index = names.index("Build with PyInstaller")
        pe_index = names.index("Verify PE architecture")
        package_index = names.index("Package into zip")
        self.assertLess(build_index, pe_index)
        self.assertLess(pe_index, package_index)
        self.assertIn("--arch x64", job["steps"][pe_index]["run"])

    def test_builds_prune_opencv_between_install_and_pyinstaller(self):
        for job_name in ("build-windows", "build-linux", "build-macos"):
            job = self.jobs[job_name]
            names = [step.get("name") for step in job["steps"]]
            install_index = names.index("Install Python dependencies")
            prune_index = names.index("Prune unused OpenCV assets")
            build_index = names.index("Build with PyInstaller")
            self.assertLess(install_index, prune_index, msg=f"{job_name} prune order")
            self.assertLess(prune_index, build_index, msg=f"{job_name} prune order")
            self.assertEqual(
                job["steps"][prune_index]["run"],
                "python scripts/prune_opencv.py",
                msg=f"{job_name} prune step",
            )
        self.assertNotIn("fix_runtime_dlls", all_run_commands(self.workflow))

    def test_windows_installs_verified_upx_before_pyinstaller(self):
        self.assertEqual(self.workflow["env"]["UPX_VERSION"], "5.2.0")
        self.assertEqual(
            self.workflow["env"]["UPX_WINDOWS_SHA256"],
            "b471ebf1b7f20f4a89150264ed9a008a2a5bfd247f3c6d1184a75bb59ca08f5d",
        )
        job = self.jobs["build-windows"]
        names = [step.get("name") for step in job["steps"]]
        install_index = names.index("Install UPX")
        build_index = names.index("Build with PyInstaller")
        self.assertLess(install_index, build_index)
        install = job["steps"][install_index]["run"]
        self.assertIn("upx-$($env:UPX_VERSION)-win64.zip", install)
        self.assertIn("Get-FileHash", install)
        self.assertIn("$env:UPX_WINDOWS_SHA256", install)
        self.assertIn("$env:GITHUB_PATH", install)
        self.assertIn("& $upx.FullName --version", install)

    def test_windows_pe_check_uses_utf8_output(self):
        step = find_step(self.jobs["build-windows"], "Verify PE architecture")
        self.assertEqual(step["env"]["PYTHONUTF8"], "1")

    def test_macos_spec_bundle_check_and_ditto(self):
        job = self.jobs["build-macos"]
        names = [step.get("name") for step in job["steps"]]
        build = names.index("Build with PyInstaller")
        verify = names.index("Verify app bundle structure")
        package = names.index("Package into zip with ditto")
        self.assertLess(build, verify)
        self.assertLess(verify, package)
        verify_run = job["steps"][verify]["run"]
        self.assertIn("check_macos_app.py", verify_run)
        self.assertIn("${{ matrix.macho }}", verify_run)
        self.assertIn("dist/mower.app", verify_run)
        self.assertNotIn("dist/mower/mower.app", verify_run)
        package_run = job["steps"][package]["run"]
        self.assertIn("ditto", package_run)
        self.assertIn("--keepParent", package_run)
        self.assertIn("dist/mower.app", package_run)
        smoke = job["steps"][names.index("Smoke launch")]["run"]
        self.assertIn('cwd="dist"', smoke)
        self.assertIn("./mower.app/Contents/MacOS/mower", smoke)

    def test_macos_keeps_zbar_system_dependency(self):
        job = self.jobs["build-macos"]
        install = find_step(job, "Install zbar system library")
        self.assertIn("brew install zbar", install["run"])

    def test_linux_smoke_checks_are_hard_failures(self):
        smoke_check = find_step(self.jobs["build-linux"], "Smoke check package")["run"]
        smoke_launch = find_step(self.jobs["build-linux"], "Smoke launch")["run"]

        self.assertIn('x64) file smoke/mower/mower | grep -q "x86-64"', smoke_check)
        self.assertIn('arm64) file smoke/mower/mower | grep -q "aarch64"', smoke_check)
        self.assertIn("ldd", smoke_check)
        self.assertIn('if [ "${missing}" -gt 0 ]', smoke_check)
        self.assertIn('if [ "${exit_code}" -eq 124 ]', smoke_launch)
        self.assertNotIn('"${exit_code}" -eq 0', smoke_launch)

    def test_linux_ldd_uses_packaged_library_directories(self):
        smoke_check = find_step(self.jobs["build-linux"], "Smoke check package")["run"]
        self.assertIn("package_library_path=", smoke_check)
        self.assertIn("find smoke/mower", smoke_check)
        self.assertIn("-printf '%h\\n'", smoke_check)
        self.assertIn(
            'LD_LIBRARY_PATH="${package_library_path}${LD_LIBRARY_PATH:+:${LD_LIBRARY_PATH}}"',
            smoke_check,
        )

    def test_pyinstaller_is_pinned_and_shared_workflow_never_pushes(self):
        self.assertEqual(self.workflow["env"]["PYINSTALLER_VERSION"], "6.22.2")
        run_commands = all_run_commands(self.workflow)
        self.assertNotIn("git push", run_commands)
        self.assertNotIn("refs/heads/", run_commands)

    def test_no_signature_secrets(self):
        for job in self.jobs.values():
            self.assertNotIn("secrets", job)
        self.assertNotIn("secrets", self.workflow.get("env", {}))


class PrepareReleaseWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = load_workflow(PREPARE_WORKFLOW_PATH)
        cls.jobs = cls.workflow["jobs"]

    def test_manual_entry_accepts_only_version(self):
        triggers = self.workflow["on"]
        self.assertEqual(
            triggers,
            {
                "workflow_dispatch": {
                    "inputs": {
                        "version": {
                            "description": "发布版本（vX.Y.Z 或 vX.Y.Z-alpha.N）",
                            "type": "string",
                            "required": True,
                        }
                    }
                }
            },
        )

    def test_prepare_and_reusable_jobs_have_explicit_permissions(self):
        self.assertEqual(self.workflow["permissions"], {})
        self.assertEqual(self.jobs["prepare"]["permissions"], {"contents": "write"})
        self.assertEqual(
            self.jobs["build-release"]["permissions"], {"contents": "write"}
        )

    def test_selected_dispatch_branch_is_the_only_branch_target(self):
        prepare = self.jobs["prepare"]
        validate = find_step(prepare, "Validate release request")
        self.assertEqual(validate["env"]["TARGET_BRANCH"], "${{ github.ref_name }}")
        self.assertEqual(validate["env"]["TARGET_REF_TYPE"], "${{ github.ref_type }}")
        self.assertIn(
            r"^v[0-9]+\.[0-9]+\.[0-9]+(-alpha\.[0-9]+)?$",
            validate["run"],
        )
        self.assertIn('"${TARGET_REF_TYPE}" != "branch"', validate["run"])

        checkout = find_step(prepare, "Checkout selected branch")
        self.assertEqual(checkout["with"]["ref"], "${{ github.ref_name }}")
        publish = find_step(prepare, "Commit selected branch and create tag")["run"]
        self.assertIn(
            '"HEAD:refs/heads/${TARGET_BRANCH}"',
            publish,
        )
        self.assertNotIn("refs/heads/alpha", publish)

    def test_write_is_limited_to_current_repository_origin(self):
        verify = find_step(
            self.jobs["prepare"], "Verify current repository and release target"
        )["run"]
        self.assertIn(
            'expected_remote="${GITHUB_SERVER_URL}/${GITHUB_REPOSITORY}"',
            verify,
        )
        self.assertIn("git remote get-url origin", verify)

        commands = all_run_commands(self.workflow)
        self.assertEqual(commands.count("git push"), 1)
        self.assertIn("git push --atomic origin", commands)
        self.assertIn('"refs/tags/${RELEASE_TAG}"', commands)
        self.assertNotIn("upstream", commands)
        self.assertNotIn("--force", commands)

    def test_version_and_changelog_are_updated_before_commit(self):
        prepare = self.jobs["prepare"]
        names = [step.get("name") for step in prepare["steps"]]
        update_index = names.index("Update version and changelog")
        publish_index = names.index("Commit selected branch and create tag")
        self.assertLess(update_index, publish_index)

        update = prepare["steps"][update_index]["run"]
        self.assertIn('python scripts/inject_version.py "${RELEASE_TAG#v}"', update)
        self.assertIn("scripts/changelog_generator.py", update)
        self.assertIn("--prepend-to CHANGELOG.md", update)

        publish = prepare["steps"][publish_index]["run"]
        self.assertIn("git add -- CHANGELOG.md arknights_mower/__init__.py", publish)
        self.assertIn('git tag -a "${RELEASE_TAG}"', publish)

    def test_release_commit_message_matches_release_type(self):
        publish = find_step(
            self.jobs["prepare"], "Commit selected branch and create tag"
        )["run"]
        self.assertIn('if [[ "${RELEASE_TAG}" == *-alpha.* ]]; then', publish)
        self.assertIn('release_kind="prerelease"', publish)
        self.assertIn('release_kind="release"', publish)
        self.assertIn(
            'git commit -m "build(release): prepare ${release_kind} ${RELEASE_TAG}"',
            publish,
        )
        self.assertNotIn("准备", publish)

    def test_tag_creation_explicitly_calls_shared_build(self):
        caller = self.jobs["build-release"]
        self.assertEqual(caller["needs"], "prepare")
        self.assertEqual(caller["uses"], "./.github/workflows/release-build.yml")
        self.assertEqual(
            caller["with"]["tag_name"],
            "${{ needs.prepare.outputs.tag_name }}",
        )
        self.assertEqual(
            caller["with"]["release_sha"],
            "${{ needs.prepare.outputs.release_sha }}",
        )
        self.assertEqual(
            self.jobs["prepare"]["outputs"],
            {
                "tag_name": "${{ steps.publish.outputs.tag_name }}",
                "release_sha": "${{ steps.publish.outputs.release_sha }}",
            },
        )


if __name__ == "__main__":
    unittest.main()
