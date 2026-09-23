import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import tempfile
import unittest
from agent_world import WorldRuntime
from ashen_vault.provision import provision


class ProvisionTests(unittest.TestCase):
    def test_private_key_is_usable_without_being_printed(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'test.sqlite3';out=Path(temp)/'private'/'identity.json'
            captured=io.StringIO()
            with redirect_stdout(captured):role=provision(db,out,'User role')
            data=json.loads(out.read_text(encoding='utf-8'))
            self.assertEqual(captured.getvalue(),'')
            self.assertEqual(data['role_id'],role)
            self.assertEqual(WorldRuntime(db).resolve_identity_token(data['identity_token'])['role_id'],role)

    def test_existing_output_is_never_overwritten_or_new_role_created(self):
        with tempfile.TemporaryDirectory() as temp:
            db=Path(temp)/'test.sqlite3';out=Path(temp)/'key.json'
            provision(db,out,'First');before=out.read_bytes()
            with self.assertRaises(FileExistsError):provision(db,out,'Second')
            self.assertEqual(out.read_bytes(),before)
            with WorldRuntime(db)._conn(readonly=True) as c:self.assertEqual(c.execute('SELECT COUNT(*) FROM roles').fetchone()[0],1)
