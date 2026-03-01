# Fix project_code and cost_center_code to allow empty strings as defaults

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0003_alter_journalline_cost_center_code_and_more'),
    ]

    # For SQLite, we need to recreate the table since ALTER COLUMN doesn't work properly
    operations = [
        migrations.RunSQL(
            # Drop and recreate with proper defaults
            sql="""
                -- Create temporary table with correct schema
                CREATE TABLE "accounting_journal_lines_new" (
                    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
                    "debit" decimal NOT NULL,
                    "credit" decimal NOT NULL,
                    "description" varchar(500) NOT NULL,
                    "created_at" datetime NOT NULL,
                    "account_id" bigint NOT NULL REFERENCES "accounting_accounts" ("id") DEFERRABLE INITIALLY DEFERRED,
                    "journal_entry_id" bigint NOT NULL REFERENCES "accounting_journal_entries" ("id") DEFERRABLE INITIALLY DEFERRED,
                    "cost_center_code" varchar(50) NOT NULL DEFAULT '',
                    "project_code" varchar(50) NOT NULL DEFAULT ''
                );
                
                -- Copy existing data
                INSERT INTO "accounting_journal_lines_new" 
                SELECT id, debit, credit, description, created_at, account_id, journal_entry_id,
                       COALESCE(cost_center_code, ''), COALESCE(project_code, '')
                FROM "accounting_journal_lines";
                
                -- Drop old table
                DROP TABLE "accounting_journal_lines";
                
                -- Rename new table
                ALTER TABLE "accounting_journal_lines_new" RENAME TO "accounting_journal_lines";
                
                -- Recreate indexes
                CREATE INDEX "accounting_journal_lines_account_id_idx" ON "accounting_journal_lines" ("account_id");
                CREATE INDEX "accounting_journal_lines_journal_entry_id_idx" ON "accounting_journal_lines" ("journal_entry_id");
                CREATE INDEX "accounting_journal_lines_cost_center_code_idx" ON "accounting_journal_lines" ("cost_center_code");
                CREATE INDEX "accounting_journal_lines_project_code_idx" ON "accounting_journal_lines" ("project_code");
            """,
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
