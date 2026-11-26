"""Guard decisions (standard library only, no spaCy needed).

    python3 -m unittest discover -s tests -t .
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GUARD = ROOT / "guard" / "guard.py"


class GuardTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.home = self.d / "home"
        self.home.mkdir()
        (self.d / "clients").mkdir()
        self.raw_csv = self.d / "clients" / "releve.csv"
        self.raw_csv.write_text("date;libelle;montant\n01/11;VIR SEPA KARIM BENALI;100\n", encoding="utf-8")
        self.raw_pdf = self.d / "clients" / "bulletin.pdf"
        self.raw_pdf.write_bytes(b"%PDF-1.4 fictif")
        self.anon = self.d / "anonymise" / "releve.anon.csv"
        self.anon.parent.mkdir()
        self.anon.write_text("date;libelle;montant\n01/11;VIR SEPA [PERSONNE_1];100\n", encoding="utf-8")
        (self.home / "produits.txt").write_text(hashlib.sha256(self.anon.read_bytes()).hexdigest() + "\n")
        self.env = dict(os.environ, ANONYMIZE_DATA_HOME=str(self.home), ANONYMIZE_DATA_PYTHON=str(self.d / "absent"))

    def tearDown(self):
        self.tmp.cleanup()

    def run_guard(self, mode, payload, env=None):
        r = subprocess.run([sys.executable, str(GUARD), mode], input=json.dumps(payload), capture_output=True,
                           text=True, env=env or self.env, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr)
        return json.loads(r.stdout) if r.stdout.strip() else None

    def tool(self, name, **inp):
        return self.run_guard("tool", {"tool_name": name, "tool_input": inp, "cwd": str(self.d)})

    def denied(self, out):
        return bool(out) and out["hookSpecificOutput"]["permissionDecision"] == "deny"

    # ------------------------------------------------------------ prompt

    def test_prompt_without_mention_passes(self):
        self.assertIsNone(self.run_guard("prompt", {"prompt": "bonjour", "cwd": str(self.d)}))

    def test_prompt_with_raw_mention_is_blocked_even_without_engine(self):
        out = self.run_guard("prompt", {"prompt": "@clients/bulletin.pdf analyse ce salaire", "cwd": str(self.d)})
        self.assertEqual(out["decision"], "block")
        self.assertIn("moteur", out["reason"])
        self.assertTrue(out["hookSpecificOutput"]["suppressOriginalPrompt"])

    def test_prompt_with_quoted_and_absolute_mentions(self):
        p = self.d / "clients" / "relevé novembre.csv"
        p.write_text("a;b\n1;2\n", encoding="utf-8")
        out = self.run_guard("prompt", {"prompt": f'regarde @"{p}" stp', "cwd": "/"})
        self.assertEqual(out["decision"], "block")
        out = self.run_guard("prompt", {"prompt": f"regarde @{self.raw_csv}, merci", "cwd": "/"})
        self.assertEqual(out["decision"], "block")

    def test_prompt_with_anonymised_copy_passes(self):
        self.assertIsNone(self.run_guard("prompt", {"prompt": "@anonymise/releve.anon.csv total ?",
                                                    "cwd": str(self.d)}))

    def test_prompt_with_text_file_or_email_passes(self):
        (self.d / "notes.md").write_text("x")
        self.assertIsNone(self.run_guard("prompt", {"prompt": "@notes.md et pablo@exemple.fr", "cwd": str(self.d)}))

    def test_copy_renamed_into_output_folder_is_still_raw(self):
        fake = self.d / "anonymise" / "copie.anon.pdf"
        fake.write_bytes(self.raw_pdf.read_bytes())
        self.assertTrue(self.denied(self.tool("Read", file_path=str(fake))))

    def test_guard_crash_blocks(self):
        r = subprocess.run([sys.executable, str(GUARD), "tool"], input="{pas du json", capture_output=True,
                           text=True, env=self.env, timeout=60)
        out = json.loads(r.stdout)
        self.assertEqual(out["hookSpecificOutput"]["permissionDecision"], "deny")
        r = subprocess.run([sys.executable, str(GUARD), "prompt"], input="{pas du json", capture_output=True,
                           text=True, env=self.env, timeout=60)
        self.assertEqual(json.loads(r.stdout)["decision"], "block")

    # ------------------------------------------------------------ tools

    def test_read_raw_denied_copy_allowed(self):
        self.assertTrue(self.denied(self.tool("Read", file_path=str(self.raw_csv))))
        self.assertTrue(self.denied(self.tool("Read", file_path="clients/bulletin.pdf")))
        self.assertIsNone(self.tool("Read", file_path=str(self.anon)))
        self.assertIsNone(self.tool("Read", file_path=str(ROOT / "README.md")))

    def test_edit_raw_denied_write_allowed(self):
        self.assertTrue(self.denied(self.tool("Edit", file_path=str(self.raw_csv), old_string="a", new_string="b")))
        self.assertIsNone(self.tool("Write", file_path=str(self.d / "clients" / "nouveau.csv"), content="x"))

    def test_registry_is_protected(self):
        self.assertTrue(self.denied(self.tool("Read", file_path=str(self.home / "produits.txt"))))
        self.assertTrue(self.denied(self.tool("Write", file_path=str(self.home / "produits.txt"), content="x")))
        self.assertTrue(self.denied(self.tool("Bash", command=f"echo abc >> {self.home}/produits.txt")))

    def test_bash_dumping_raw_denied(self):
        for cmd in ["cat clients/releve.csv", "head -5 clients/releve.csv | sort", "grep KARIM clients/*.csv",
                    "python3 -c \"print(open('clients/releve.csv').read())\"", "cp clients/releve.csv x.txt",
                    "git diff clients/releve.csv", "find clients -name '*.csv' -exec cat {} \\;",
                    "ls clients/*.csv | xargs cat", "cat $(ls clients/*.csv)", "pdftotext clients/bulletin.pdf -",
                    "python3 - <<EOF\nprint(open('clients/releve.csv').read())\nEOF", "cat clients/*",
                    "unzip -p clients/bulletin.pdf", "cd clients && cat releve.csv", "rg KARIM clients",
                    "python3 analyse.py clients", "git log -p clients/releve.csv", "git diff", "git show HEAD"]:
            with self.subTest(cmd=cmd):
                self.assertTrue(self.denied(self.tool("Bash", command=cmd)), cmd)

    def test_bash_harmless_allowed(self):
        for cmd in ["ls clients", "ls -la clients/releve.csv", "git add clients/releve.csv", "git status",
                    "wc -l clients/releve.csv", "anonymiser clients/releve.csv", "cat anonymise/releve.anon.csv",
                    "python3 analyse.py", "node gen-deck.js", "echo fini", "open clients/bulletin.pdf",
                    "mkdir -p anonymise && anonymiser clients", "git push", "git log --oneline -- README.md", "git log --oneline", "git stash"]:
            with self.subTest(cmd=cmd):
                self.assertIsNone(self.tool("Bash", command=cmd), cmd)

    def test_grep(self):
        self.assertTrue(self.denied(self.tool("Grep", pattern="KARIM", path=str(self.raw_csv))))
        self.assertTrue(self.denied(self.tool("Grep", pattern="KARIM", path=str(self.d))))
        self.assertTrue(self.denied(self.tool("Grep", pattern="KARIM", path=str(self.d), glob="*.csv")))
        self.assertIsNone(self.tool("Grep", pattern="KARIM", path=str(self.d), glob="*.py"))
        self.assertIsNone(self.tool("Grep", pattern="KARIM", path=str(self.d), glob="!*.csv"))
        self.assertIsNone(self.tool("Grep", pattern="KARIM", path=str(self.d / "anonymise")))

    def test_names_found_by_the_guard_are_not_revealed(self):
        secret = self.d / "clients" / "Bulletin_QUENTOVIC_Bertrand.csv"
        secret.write_text("a;b\n", encoding="utf-8")
        for out in [self.tool("Grep", pattern="x", path=str(self.d / "clients")),
                    self.tool("Bash", command="rg x clients"), self.tool("Bash", command="cat clients/*.csv")]:
            self.assertTrue(self.denied(out))
            self.assertNotIn("QUENTOVIC", out["hookSpecificOutput"]["permissionDecisionReason"])

    def test_huge_folder_is_denied_not_skipped(self):
        big = self.d / "gros"
        big.mkdir()
        for i in range(5005):
            (big / f"f{i}.txt").touch()
        self.assertTrue(self.denied(self.tool("Grep", pattern="x", path=str(big))))
        self.assertTrue(self.denied(self.tool("Bash", command="rg x gros")))

    def test_other_tools_pass(self):
        self.assertIsNone(self.tool("Glob", pattern="**/*.csv"))
        self.assertIsNone(self.tool("WebSearch", query="x"))


if __name__ == "__main__":
    unittest.main()
