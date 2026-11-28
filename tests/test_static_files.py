import os
import tempfile
import unittest
import subprocess
import sys
from unittest.mock import patch

import main


class SyncStaticFilesTests(unittest.TestCase):
    def write_file(self, path, content):
        directory = os.path.dirname(path)
        if not os.path.isdir(directory):
            os.makedirs(directory)
        with open(path, "w", encoding="utf-8") as file_obj:
            file_obj.write(content)

    def read_file(self, path):
        with open(path, "r", encoding="utf-8") as file_obj:
            return file_obj.read()

    def create_directory_link(self, link_path, target_path):
        """Windowsでは管理者権限不要のジャンクションを作成し、他OSではsymlinkを使用する。"""
        if sys.platform == "win32":
            try:
                subprocess.check_call(
                    ["cmd", "/c", "mklink", "/J", link_path, target_path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            except (OSError, subprocess.CalledProcessError):
                self.skipTest("Windowsジャンクションを作成できない環境です")
        else:
            try:
                os.symlink(target_path, link_path, target_is_directory=True)
            except (OSError, NotImplementedError):
                self.skipTest("ディレクトリシンボリックリンクを作成できない環境です")

    def remove_directory_link(self, link_path):
        """TemporaryDirectoryの後始末時にリンク先を辿らないよう、リンク自体を先に削除する。"""
        if sys.platform == "win32":
            os.rmdir(link_path)  # junction自体を削除し、リンク先のディレクトリは保持する
        else:
            os.unlink(link_path)

    def test_creates_target_and_copies_bundled_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "source")
            target = os.path.join(temp_dir, "output", "static")
            self.write_file(os.path.join(source, "css", "style.css"), "bundled-css")

            main.sync_static_files(source, target)

            self.assertEqual(
                self.read_file(os.path.join(target, "css", "style.css")),
                "bundled-css",
            )

    def test_preserves_user_files_and_directories_and_overwrites_bundled_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "source")
            target = os.path.join(temp_dir, "output", "static")
            self.write_file(os.path.join(source, "css", "style.css"), "new-standard-css")
            self.write_file(os.path.join(source, "images", "logo.png"), "bundled-image")
            self.write_file(os.path.join(target, "css", "style.css"), "old-css")
            self.write_file(os.path.join(target, "css", "custom.css"), "custom-css")
            self.write_file(os.path.join(target, "images", "custom.png"), "custom-image")
            self.write_file(os.path.join(target, "user-folder", "notes.txt"), "user-notes")

            main.sync_static_files(source, target)

            self.assertEqual(
                self.read_file(os.path.join(target, "css", "style.css")),
                "new-standard-css",
            )
            self.assertEqual(
                self.read_file(os.path.join(target, "images", "logo.png")),
                "bundled-image",
            )
            self.assertEqual(
                self.read_file(os.path.join(target, "css", "custom.css")),
                "custom-css",
            )
            self.assertEqual(
                self.read_file(os.path.join(target, "images", "custom.png")),
                "custom-image",
            )
            self.assertEqual(
                self.read_file(os.path.join(target, "user-folder", "notes.txt")),
                "user-notes",
            )

    def test_path_type_conflict_fails_before_existing_files_are_changed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "source")
            target = os.path.join(temp_dir, "output", "static")
            self.write_file(os.path.join(source, "css", "style.css"), "bundled-css")
            self.write_file(os.path.join(source, "images", "logo.png"), "bundled-image")
            self.write_file(os.path.join(target, "css", "style.css"), "existing-css")
            self.write_file(os.path.join(target, "images", "logo.png", "nested.txt"), "conflict")

            with self.assertRaises(OSError):
                main.sync_static_files(source, target)

            self.assertEqual(
                self.read_file(os.path.join(target, "css", "style.css")),
                "existing-css",
            )
            self.assertEqual(
                self.read_file(os.path.join(target, "images", "logo.png", "nested.txt")),
                "conflict",
            )

    def test_missing_source_does_not_damage_target(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "missing-source")
            target = os.path.join(temp_dir, "output", "static")
            self.write_file(os.path.join(target, "custom.css"), "keep-me")

            with self.assertRaises(FileNotFoundError):
                main.sync_static_files(source, target)

            self.assertEqual(
                self.read_file(os.path.join(target, "custom.css")),
                "keep-me",
            )

    def test_copy_failure_preserves_existing_standard_file_and_cleans_temp_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "source")
            target = os.path.join(temp_dir, "output", "static")
            self.write_file(os.path.join(source, "css", "style.css"), "new-css")
            self.write_file(os.path.join(target, "css", "style.css"), "old-css")

            with patch("main.shutil.copyfile", side_effect=OSError("simulated copy failure")):
                with self.assertRaises(OSError):
                    main.sync_static_files(source, target)

            self.assertEqual(
                self.read_file(os.path.join(target, "css", "style.css")),
                "old-css",
            )
            self.assertEqual(
                os.listdir(os.path.join(target, "css")),
                ["style.css"],
            )


    def test_rejects_target_static_directory_link_without_modifying_external_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "source")
            outside = os.path.join(temp_dir, "outside")
            target = os.path.join(temp_dir, "output", "static")
            self.write_file(os.path.join(source, "css", "style.css"), "bundled-css")
            self.write_file(os.path.join(outside, "css", "style.css"), "external-original")
            os.makedirs(os.path.dirname(target))
            self.create_directory_link(target, outside)
            try:
                with self.assertRaises(OSError):
                    main.sync_static_files(source, target)

                self.assertEqual(
                    self.read_file(os.path.join(outside, "css", "style.css")),
                    "external-original",
                )
            finally:
                self.remove_directory_link(target)

    def test_rejects_nested_directory_link_without_modifying_external_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source = os.path.join(temp_dir, "source")
            target = os.path.join(temp_dir, "output", "static")
            outside = os.path.join(temp_dir, "outside")
            self.write_file(os.path.join(source, "css", "style.css"), "bundled-css")
            self.write_file(os.path.join(target, "keep.txt"), "existing-user-file")
            self.write_file(os.path.join(outside, "style.css"), "external-original")
            link_path = os.path.join(target, "css")
            self.create_directory_link(link_path, outside)
            try:
                with self.assertRaises(OSError):
                    main.sync_static_files(source, target)

                self.assertEqual(
                    self.read_file(os.path.join(outside, "style.css")),
                    "external-original",
                )
                self.assertEqual(
                    self.read_file(os.path.join(target, "keep.txt")),
                    "existing-user-file",
                )
            finally:
                self.remove_directory_link(link_path)

if __name__ == "__main__":
    unittest.main()
