set colsep      ;
set headsep off  ;
set pagesize 0   ;
set trimspool on ;
set heading OFF  ;
set FEEDBACK OFF ;
set markup csv on;



Spool '{{SPOOL_CSV_PATH}}';
---{{TABLE_NAME}}
select
/*csv*/
distinct
{{SELECT_COLUMNS}}
from {{TABLE_NAME}} WHERE STATUS = 'V' AND {{BATCH_COLUMN}} = :p_batch_id;
spool OFF;
