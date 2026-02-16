We are going to build a Conversion Agent which will be responsible in validating,  transforming and help in creating the Load File for Oracle ERP system.
We will create agentic skills for each step so that it would be easier to manage or update how each step works.

STEP 1:
Get the Interface table doc link from config.json -> interface_table_doc key
Now make a REST GET API CALL to the link we get https://docs.oracle.com/en/cloud/saas/sales/oedms/hzimppartiest-12933.html
In the API HTML Response
Look for Columns table - <table class="customlayout" style="table-layout: auto; width: 95%" summary="Columns">

Fetch Headings, Rows data for  -> Name, Datatype, Length, Precision, Not-null, status


STEP 2: 
Using the csv from STEP 1 we have to create a Oracle SQL query to create table, create the .sql file in the /output folder. 
Make sure to follow the DataType, Precision and Not Null definitions for each column. Use table_name from config.json for the table name

Once this is done, we have to create a SQL connection using atp_username, atp_password, atp_wallet_file_path, atp_service from config.json and run the create table SQL. 


STEP 3: 

Based on the mapping_sheet_path in the config.json,
We have to create an Oracle PLSQL package - pks, pkb to perform the mandatory, validations first and then the transformations if any on the columns mentioned in the sheet.
I am giving some sample packages, in the /samples folders so you can get an understanding of how it's usually done the validations, the error handling. 



STEP 4: 

Based on the ctl_file_path in the config.json,
We have to create a Spool query and pick the columns from the atp table in the same order that they are mentioned in ctl file.
- example "C:\Users\nvishwatej\Desktop\Conversion Agent\samples\PEG_CONV03_HZ_IMP_LOCATIONS_T_Spool_Query.sql"

The created spool sql query should be in the /output folder