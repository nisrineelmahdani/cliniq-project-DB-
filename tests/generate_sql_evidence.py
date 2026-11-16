"""Generate actual SQL evidence only in cliniq_test_dev; reset confirmation required.

python -m tests.generate_sql_evidence --output docs/sql_evidence.json
No development credentials, database, global settings or patient records are used.
"""

import argparse
import json
import os
from pathlib import Path

from database.setup import run_script
from tests.mysql_support import DedicatedDatabase,reset_schema
from tests.sql_validation_support import (queries,index_inventory,explain,analyze,populate_benchmark,
                                         trigger_restriction_probe,SEED_PARAMS,BENCHMARK_PARAMS,workload_counts)


def collect_evidence():
    if os.getenv('CLINIQ_TEST_SQL_EXTENSIONS')=='1':
        raise ValueError('Use CLINIQ_TEST_SQL_EXTENSIONS=0 to capture an unindexed baseline.')
    evidence={}
    with DedicatedDatabase().prepared() as database:
        connection=database.connect()
        try:
            with connection.cursor(dictionary=True) as cursor:
                cursor.execute('SELECT DATABASE() AS database_name,VERSION() AS version,@@GLOBAL.log_bin AS log_bin,@@GLOBAL.log_bin_trust_function_creators AS log_bin_trust_function_creators')
                evidence['server']=cursor.fetchone()
                evidence['queries']=[]
                for query in queries():
                    cursor.execute(query['sql'])
                    rows=cursor.fetchall()
                    evidence['queries'].append(dict(id=query['id'],objective=query['objective'],rows=len(rows)))
            evidence['hospitalization_probe']=trigger_restriction_probe(connection)
            evidence['seed']={'rows':workload_counts(connection),'indexes_before':index_inventory(connection)}
            run_script(connection,'03_triggers.sql')
            analyze(connection)
            evidence['seed']['before']=explain(connection,SEED_PARAMS)
            run_script(connection,'05_indexes.sql')
            analyze(connection)
            evidence['seed']['after']=explain(connection,SEED_PARAMS)
            evidence['seed']['indexes_after']=index_inventory(connection)
            # Rebuild ONLY the authorized test schema for a comparable unindexed
            # larger run, avoiding ad hoc removal of FK-supporting indexes.
            reset_schema(connection)
            run_script(connection,'03_triggers.sql')
            populate_benchmark(connection)
            evidence['benchmark']={'generated_per_table':12000,'rows':workload_counts(connection),'indexes_before':index_inventory(connection)}
            analyze(connection)
            evidence['benchmark']['before']=explain(connection,BENCHMARK_PARAMS)
            run_script(connection,'05_indexes.sql')
            analyze(connection)
            evidence['benchmark']['after']=explain(connection,BENCHMARK_PARAMS)
            evidence['benchmark']['indexes_after']=index_inventory(connection)
            evidence['notes']=['EXPLAIN rows/filtered sont des estimations, pas des temps mesurés.',
                               'Aucun gain de durée d’exécution n’est affirmé.',
                               'Le dataset synthétique n’existe que pendant cette session de test.']
        finally:
            connection.rollback()
            connection.close()
    return evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    evidence=collect_evidence()
    args.output.write_text(json.dumps(evidence,default=str,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(f'Evidence written: {args.output}; test seed restored; no development changes.')


if __name__=='__main__':
    main()
