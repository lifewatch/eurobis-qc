from dbworks.create_lookup_tables import import_files
import_files()

from eurobisqc.examples import run_mssql_whole_db
from eurobisqc.examples import fitness_for_use
run_mssql_whole_db.process_all_db(True, True)
fitness_for_use.run()
