import os
from logging.config import fileConfig
from sqlalchemy import engine_from_config, pool
from alembic import context

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Allow DATABASE_URL env var to override alembic.ini (used in CI and production)
db_url = os.environ.get("DATABASE_URL")
if db_url:
    config.set_main_option("sqlalchemy.url", db_url)

from app.db.session import Base  # noqa: E402

# F34 — import EVERY model module, by walking the package.
#
# This was a hand-maintained list of three: user, transaction, budget. Six
# others (bank_connection, categorisation_rule, fx_rate, import_mapping,
# savings_goal, tag) had been added since and never appeared here, so
# `target_metadata` did not know they existed. Two consequences, both of which
# had already happened: `--autogenerate` could not see them (every one of their
# migrations had to be hand-written, and the history drifted until it contained
# a duplicate revision id and a cycle), and an autogenerate run today would have
# proposed DROPPING all six as tables-not-in-the-models.
#
# A list that must be updated by hand every time a model is added is a list that
# will be wrong. Walking the package cannot go stale.
import pkgutil                     # noqa: E402
import importlib                   # noqa: E402
import app.models                  # noqa: E402

for _m in pkgutil.iter_modules(app.models.__path__):
    importlib.import_module(f"app.models.{_m.name}")

target_metadata = Base.metadata

# F34 — never let autogenerate touch anything that is not finly's.
#
# finly shares one Supabase project with four other apps, each fenced into its
# own schema. `finly_app`'s search_path is `finly, extensions`, so PostGIS's
# `spatial_ref_sys` is VISIBLE — and the first autogenerate run duly proposed
# `op.drop_table('spatial_ref_sys')`, because it is a table Alembic can see that
# the models do not define. That table is shared: Poly_Tracker's `poly` schema
# is PostGIS-backed off the same extension. Running that migration would have
# broken a different app.
#
# "Reviewed the generated migration carefully" is not a control. This is.
def include_object(obj, name, type_, reflected, compare_to):
    schema = getattr(obj, "schema", None)
    if schema not in (None, "finly"):
        return False
    # Anything reflected that the models do not define is somebody else's.
    if type_ == "table" and reflected and compare_to is None:
        return False
    return True


def run_migrations_offline():
    context.configure(url=config.get_main_option("sqlalchemy.url"), target_metadata=target_metadata, literal_binds=True, include_object=include_object)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online():
    connectable = engine_from_config(config.get_section(config.config_ini_section), prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, include_object=include_object)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
