#!/usr/bin/python
##############################################################################
# INTEL CONFIDENTIAL
#
# Copyright 2015 Intel Corporation All Rights Reserved.
#
# The source code contained or described herein and all documents related to
# the source code (Material) are owned by Intel Corporation or its suppliers
# or licensors. Title to the Material remains with Intel Corporation or its
# suppliers and licensors. The Material may contain trade secrets and
# proprietary and confidential information of Intel Corporation and its
# suppliers and licensors, and is protected by worldwide copyright and trade
# secret laws and treaty provisions. No part of the Material may be used,
# copied, reproduced, modified, published, uploaded, posted, transmitted,
# distributed, or disclosed in any way without Intel's prior express written
# permission.
#
# No license under any patent, copyright, trade secret or other intellectual
# property right is granted to or conferred upon you by disclosure or
# delivery of the Materials, either expressly, by implication, inducement,
# estoppel or otherwise. Any license under such intellectual property rights
# must be express and approved by Intel in writing.
##############################################################################

# TODO: Update this docstring to reflect the new usage.

"""
Requirements:
    Clouderas python cm-api http://cloudera.github.io/cm_api/
    working Cloudera manager with at least a single cluster
    Intel Analytics installation
    sudo access

This script queries Cloudera manager to get the host names of the machines running the following roles.
 -ZOOKEEPER server(the zookeeper role is actually called 'server')
 -HDFS name node
 -SPARK master
It also updates the spark-env.sh config in Cloudera manager with a necessary export of SPARK_CLASSPATH
needed for graph processing. The spark service config is re-deployed and the service is restarted.
If the Intel Analytics class path is already present no updates are done,
the config is not deployed and the spark service is not restarted.

CAUTION:
    You can run this script many times to pull the latest configuration details from Cloudera manager but care should
    be taken when getting asked the questions to configure the database. If any existing database configurations exist
    you will be asked if you would like to skip the database configuration and default to previous settings or
    continue with fresh settings. If you do change database configurations the Intel Analytics rest server will loose
    all knowledge of any frames, graphs and other processed data that might have been created.

Command Line Arguments
    Every command line argument has a corresponding user prompt. If the command line argument is given the prompt will
    be skipped.
--host the cloudera manager host address. If this script is run on host managed by Cloudera manager we will try to get
    the host name from /etc/cloudera-scm-agent/config.ini

--port the Cloudera manager port. The port used to access the Cloudera manager ui. Defaults to 7180 if nothing is
    entered when prompted

--username The Cloudera manager user name. The user name for loging into Cloudera manager

--pasword The Cloudera manager pass word. The user name for loging into Cloudera manager

--cluster The Cloudera cluster we will pull and update config for. If Cloudera manager manages more than one cluster
    we need to know what cluster we will be updating and pulling our config for. Can give the display name of the
    cluster

--restart Weather or not we will restart the spark service after setting the spark classpath. After the SPARK_CLASSPATH
    gets updated we deploy the new config but we also need to restart the spark service for the changes to take effect
    on all the master and worker nodes. This is left to the user to decide in case spark is currently busy running some
    jobs

--db_only configure only the database yes/no

--db-host the hostname of your postgres database. will default to localhost

--db-port the port number for your postgres installation. will default to 5432

--db the postgres database name. will default to ia_metastore

--db-username the database user name. will default to iauser

--db-password the database password. will default to random hash. Don't use '$' sign in the password the intel analytics
    server can't read them correctly from the configuration file. While doing the configuration for the password
    you will only see asterisk for the display. If you need the password for future reference you can open the
    application.conf file and look for metastore.connection-postgresql.username.

--db-reconfig weather or not you want to re configure the database. yes/no

"""

from __future__ import print_function
import os
import sys
import argparse
import cluster_config as cc
from cluster_config import cli
from cluster_config.const import Const
from cluster_config.cdh.cluster import Cluster, save_config
import cluster_config.cdh as cdh
import time, datetime
from pprint import pprint
from os import system
import hashlib, re, time, argparse, os, time, sys, getpass
import codecs

IAUSER = "atkuser"
SPARK_USER = "spark"
LIB_PATH = "/usr/lib/trustedanalytics/graphbuilder/lib/ispark-deps.jar"
IA_LOG_PATH = "/var/log/trustedanalytics/rest-server/output.log"
IA_START_WAIT_LOOPS = 30
IA_START_WAIT = 2
POSTGRES_WAIT = 3

GOOD = '\033[92m'
WARNING = '\033[93m'
ERROR = '\033[91m'
RESET = '\033[0m'


def color_text(text, color):
    return text


# def restart_service(service):  DELETEME?
#     """
#     restart the service
#     :param service: service we are going to restart

#     """
#     print "\nYou need to restart " + service.name + " service for the config changes to take affect."
#     service_restart = get_arg("Would you like to restart spark now? Enter \"" + color_text("yes", GOOD) +
#                               "\" to restart.", "no", args.restart)
#     if service_restart is not None and service_restart.strip().lower() == "yes":
#         print "Restarting " + service.name,
#         service.restart()
#         poll_commands(service, "Restart")
#         print color_text("Restarted " + service.name, GOOD)


# def update_spark_env(group, spark_config_env_sh):# DELETEME?

#     """
#     update the park env configuration in Cloudera manager

#     :param group: the group that spark_env.sh belongs too
#     :param spark_config_env_sh: the current spark_env.sh value
#     :return:
#     """

#     if spark_config_env_sh is None:
#         spark_config_env_sh = ""

#     #look for any current SPARK_CLASSPATH
#     found_class_path = find_exported_class_path(spark_config_env_sh)

#     if found_class_path is None:
#         #no existing class path found
#         print "No current SPARK_CLASSPATH set."

#         updated_class_path = create_updated_class_path(found_class_path, spark_config_env_sh)

#         print "Setting to: " + updated_class_path

#         #update the spark-env.sh with our exported class path appended to whatever whas already present in spark-env.sh
#         group.update_config({"SPARK_WORKER_role_env_safety_valve": updated_class_path})
#         return True
#     else:
#         #found existing classpath
#         found_class_path_value = find_class_path_value(spark_config_env_sh)
#         print "Found existing SPARK_CLASSPATH: " + found_class_path_value

#         #see if we our LIB_PATH is set in the classpath
#         found_ia_class_path = find_ia_class_path(found_class_path_value)
#         if found_ia_class_path is None:
#             #no existing ia classpath
#             print "No existing Intel Analytics class path found."
#             updated_class_path = create_updated_class_path(found_class_path_value, spark_config_env_sh)
#             print "Updating to: " + updated_class_path
#             group.update_config({"SPARK_WORKER_role_env_safety_valve" : updated_class_path})
#             return True
#         else:
#             #existing ia classpath
#             print "Found existing Intel Analytics class path no update needed."
#             return False
#     return False


# def get_hdfs_details(services):  # DELETEME?

#     """
#     We need various hdfs details to eventually get to the name node host name

#     :param services: all the cluster services
#     :return: name node host name
#     """
#     #get hdfs service details
#     hdfs_service = find_service(services, "HDFS")
#     if hdfs_service is None:
#         print color_text("no hdfs service found", ERROR)
#         exit(1)

#     hdfs_roles = hdfs_service.get_all_roles()

#     hdfs_namenode_roles = find_service_roles(hdfs_roles, "NAMENODE")

#     hdfs_namenode_role_hostnames = get_role_host_names(api, hdfs_namenode_roles)

#     hdfs_config_groups = role_config_groups.get_all_role_config_groups(api, hdfs_service.name, cluster.name)

#     hdfs_namenode_port, _ = find_config(hdfs_config_groups, "hdfs-NAMENODE-BASE", "namenode_port")

#     return hdfs_namenode_role_hostnames, hdfs_namenode_port


# def get_zookeeper_details(services):# DELETEME  ??
#     #  Assigned during CDH deploy and available via query through the Cluster object.
#     """
#     get the various zookeeper service details and eventually return the zookeeper host names

#     :param services: all the cluster services
#     :return: list of zookeeper host names
#     """
#     zookeeper_service = find_service(services, "ZOOKEEPER")
#     if zookeeper_service is None:
#         print color_text("no zookeeper service found", ERROR)
#         exit(1)

#     zookeeper_roles = zookeeper_service.get_all_roles()

#     zookeeper_server_roles = find_service_roles(zookeeper_roles, "SERVER")

#     zookeeper_server_role_hostnames = get_role_host_names(api, zookeeper_server_roles)

#     zookeeper_config_groups = role_config_groups.get_all_role_config_groups(api, zookeeper_service.name, cluster.name)

#     zookeeper_client_port, _ = find_config(zookeeper_config_groups, "zookeeper-SERVER-BASE", "clientPort")

#     return zookeeper_server_role_hostnames, zookeeper_client_port


# def get_spark_details(services):
#     """
#     Look for the spark master host name, spark master port, executor memory and update the spark_env.sh with the
#     necessary class path to build graphs
#     :param services: all the cluster services
#     :return: spark master host name, port and executor max memory
#     """
#     spark_service = find_service(services, "SPARK")
#     if spark_service is None:
#        print color_text("no spark service found", ERROR)
#        exit(1)

#     spark_roles = spark_service.get_all_roles()

#     spark_master_roles = find_service_roles(spark_roles, "SPARK_MASTER")

#     spark_master_role_hostnames = get_role_host_names(api, spark_master_roles)

#     spark_config_groups = role_config_groups.get_all_role_config_groups(api, spark_service.name, cluster.name)

#     spark_config_executor_total_max_heapsize, _ = find_config(spark_config_groups, "spark-SPARK_WORKER-BASE",
#                                                            "executor_total_max_heapsize")

#     spark_config_master_port, _ = find_config(spark_config_groups, "spark-SPARK_MASTER-BASE", "master_port")

#     #spark_config_env_sh, group = find_config(spark_config_groups, "spark-GATEWAY-BASE",
#     #                               "spark-conf/spark-env.sh_client_config_safety_valve")
#     #spark_config_env_sh, group = find_config(spark_config_groups, "spark-SPARK_WORKER-BASE",
#                                              #"SPARK_WORKER_role_env_safety_valve")

#     #updated = update_spark_env(group, spark_config_env_sh)

#     #if updated and True:
#     #    deploy_config(spark_service, spark_roles)
#     #    restart_service(spark_service)

#     return spark_master_role_hostnames, spark_config_executor_total_max_heapsize, spark_config_master_port


def search_config(config_key, group_name, search_text):
    """
    centralize the config search since i was doing the same exact search on every config key lookup
    :param config_key: the config key from our application.conf
    :param group_name: The name of the regex group. makes it easy to find later
    :param search_text: the application.conf text to search in
    :return: the parameter as a string, or None if 'config_key' not found in 'search_text'
    """
    matches = re.search(r'' + config_key + ' = "(?P<' + group_name + '>.*)"', search_text)
    if matches:
        return matches.group(group_name)
    else:
        return None


def test_old_cdh_conf():
    """Check for an old cdh.conf file.  Unlike in the old
    (pre-OSS-release) version of the config script, there are no
    default values assumed for any of the configuration parameters.
    Whether there is an existing cdh.conf file or not, a new one will
    be written.  If new parameters are not passed in on the command
    line, we will generate warnings.
    """
    try:
        cdh_conf = codecs.open("cdh.conf", encoding="utf-8", mode="r")
        cdh_conf_text = cdh_conf.read()
        cdh_conf.close()
    except:
        raise ConfigurationException("Missing or invalid cdh.conf file")
    finally:
        return


def get_old_db_details():
    """Get the old database settings if we have any. Unlike in the old
    (pre-OSS-release) version of the config script, there are no
    default values assumed for any of the configuration parameters.
    If there is an existing db.conf file, parameters there are used,
    unless they are overridden on the command line.
    """
    db_conf_prelim = {
        'host': None,
        'port': None,
        'database': None,
        'username': None,
        'password': None }

    db_conf = codecs.open("db.conf", encoding="utf-8", mode="r")
    db_conf_text = db_conf.read()
    db_conf.close()

    prev_host = search_config("metastore.connection-postgresql.host", "host", db_conf_text)
    prev_port = search_config("metastore.connection-postgresql.port", "port", db_conf_text)
    prev_database = search_config("metastore.connection-postgresql.database", "database", db_conf_text)
    prev_username = search_config("metastore.connection-postgresql.username", "username", db_conf_text)
    prev_password = search_config("metastore.connection-postgresql.password", "password", db_conf_text)
    db_conf_from_file = {
        'host':     prev_host     if prev_host     else None,
        'port':     prev_port     if prev_port     else None,
        'database': prev_database if prev_database else None,
        'username': prev_username if prev_username else None,
        'password': prev_password if prev_password else None }

    db_conf_prelim.update(db_conf_from_file)
    return db_conf_prelim


def set_db_user_access(db_username):
    """
    set the postgres user access in pg_hba.conf file. We will only ever set localhost access. More open permissions
    will have to be updated by a system admin. The access ip rights gets appended to the top of the postgres conf
    file. repeated calls will keep appending to the same file.

    :param db_username: the database username
    """
    #update pg_hba conf file with user entry will only ever be for local host
    print "Configuring postgres access for  \"" + db_username + "\" "
    try:
        pg_hba = codecs.open(r"/var/lib/pgsql/data/pg_hba.conf", encoding="utf-8", mode="r+")
    except IOError:
        system("service postgresql initdb")
        pg_hba = codecs.open(r"/var/lib/pgsql/data/pg_hba.conf", encoding="utf-8", mode="r+")

    pg_hba_text = pg_hba.read()
    pg_hba.seek(0)
    pg_hba.write("host    all         " + db_username + "      127.0.0.1/32            md5 #IATINSERT\n" + pg_hba_text)
    pg_hba.close()

    restart_db()


def create_db_user(db_username, db_password):
    """
    create the postgres user and set his password. Will do a OS system call to the postgres psql command to create the
    user.

    :param db_username: the  user name that will eventually own the database
    :param db_password: the password for the user
    """
    print system("su -c \"echo \\\"create user " + db_username +
                 " with createdb encrypted password '" + db_password + "';\\\" | psql \"  postgres")


def create_db(db, db_username):
    """
    Create the database and make db_username the owner. Does a system call to the postgres psql command to create the
    database

    :param db: the name of the database
    :param db_username: the postgres user that will own the database

    """
    print system("su -c \"echo \\\"create database " + db + " with owner " + db_username + ";\\\" | psql \"  postgres")


def create_IA_metauser(db):
    """
    Once postgres is configured and the IA server has been restarted we need to add the test user to so authentication
    will work in IA. Does a psql to set the record

    :param db: the database we will be inserting the record into

    """
    print system("su -c \" echo \\\" \c " + db +
                 "; \\\\\\\\\  insert into users (username, api_key, created_on, modified_on) "
                 "values( 'metastore', 'test_api_key_1', now(), now() );\\\" | psql \" postgres ")


def restart_db():
    """
    We need to restart the postgres server for the access updates to pg_hba.conf take affect. I sleep right after to
    give the service some time to come up

    :return:
    """
    print system("service postgresql  restart ")
    time.sleep(POSTGRES_WAIT)


def get_IA_log():
    """
    Open the output.log and save the contents to memory. Will be used monitor the IA server restart status.
    :return:
    """
    try:
        output_log = codecs.open(IA_LOG_PATH, encoding="utf-8", mode="r")
        output_log_text = output_log.read()
        output_log.close()
        return output_log_text
    except IOError:
        return ""


def restart_IA():
    """
    Send the linux service command to restart trustedanalytics analytics server and read the output.log file to see when the server
    has been restarted.
    :return:
    """
    #Truncate the IA log so we can detect a new 'Bound to' message which would let us know the server is up
    try:
        output_log = codecs.open(IA_LOG_PATH, encoding="utf-8", mode="w+")
        output_log.write("")
        output_log.close()
    except IOError:
        print "Starting trustedanalytics analytics"

    #restart IA
    print system("service trustedanalytics restart ")
    print "Waiting for trustedanalytics analytics server to restart"

    output_log_text = get_IA_log()
    count = 0
    #When we get the Bound to message the server has finished restarting
    while re.search("Bound to.*:.*", output_log_text) is None:
        print " . ",
        sys.stdout.flush()
        time.sleep(IA_START_WAIT)

        output_log_text = get_IA_log()

        count += 1
        if count > IA_START_WAIT_LOOPS:
            print color_text("Intel Analytics Rest server didn't restart", ERROR)
            exit(1)

    print "\n"


def set_db_details(db, db_username, db_password):
    """
    Update the local host Postgres install. Create the user, database and set network access.
    :param db: database name
    :param db_username: db user name
    :param db_password: db password

    """
    set_db_user_access(db_username)
    create_db_user(db_username, db_password)
    create_db(db, db_username)
    restart_db()
    restart_IA()
    create_IA_metauser(db)
    print color_text("Postgres is configured.", GOOD)


def cli(parser=None):
    if parser is None:
        parser = argparse.ArgumentParser(description="Configure a new ATK install")
        parser.add_argument("--host", type=str, help="Cloudera Manager Host", required=True)
        parser.add_argument("--port", type=int, help="Cloudera Manager Port", required=True)
        parser.add_argument("--username", type=str, help="Cloudera Manager User Name", required=True)
        parser.add_argument("--password", type=str, help="Cloudera Manager Password", required=True)
        parser.add_argument("--cluster", type=str,
                            help="Cloudera Manager Cluster Name if more than one cluster is "
                            "managed by Cloudera Manager.", default="cluster")
        parser.add_argument("--db_only", type=str, help="configure only the database yes/no", required=True)
        parser.add_argument("--db_host", type=str, help="Database host name")
        parser.add_argument("--db_port", type=str, help="Database port number")
        parser.add_argument("--db", type=str, help="Database name")
        parser.add_argument("--db_username", type=str, help="Database username")
        parser.add_argument("--db_password", type=str, help="Database password")
        parser.add_argument("--path", type=str,
                            help="Directory to save new configuration files "
                            "and read old ones (if present). "
                            "Defaults to working directory {0}".format(os.getcwd()))
        parser.add_argument("--log", type=str, help="Log level [INFO|DEBUG|WARNING|FATAL|ERROR]", default="INFO",
                            choices=["INFO", "DEBUG", "WARNING", "FATAL", "ERROR"])
    return parser


def create_config(identifier, prefix, confs, filename):
    path = file.file_path(filename, args.path)
    configfile = codecs.open(config_file_path, encoding="utf-8", mode="w")
    for key in confs:
        print("{0}.{1}={2}".format(prefix, key, confs[key]), file=f)
    f.close()
    log.info("Wrote generated {0} configuration file to: {1}".format(identifier, path))
    print color_text("Configuration created for Intel Analytics: {0}".format(identifier), GOOD)


def run(args, cluster=None):
    # Take what is on the commandline for CDH initial parameters, if anything.
    cdh_conf_from_commandline = {
        'username': args.username if args.username else None,
        'password': args.password if args.password else None }

    # Query Cloudera for the parameters we can get from it using the
    # config_cluster API.  Login and password must be provided on the
    # commandline.
    # FIXME - Do we need error checking of username and password here,
    # or is that done in the Cluster constructor?
    if cluster is None:
        cluster = Cluster(args.host, args.port, args.username, args.password, args.cluster)

    # FIXME - Are these calls to the cluster_config API correct for
    # these parameters to write to cdh.conf?
    yarn_host_names = []
    for host in cluster.yarn.nodemanager.hosts.hosts:
        yarn_host_names.append(cluster.yarn.nodemanager.hosts[host].hostname)
    zookeeper_client_port = cluster.zookeeper.server.server_base.clientport.get()
    cdh_conf.port = cluster.hdfs.namenode.namenode_base.namenode_port.get()
    cdh_conf.host = cluster.hdfs.namenode.hosts.hostnames()[0]

    cdh_conf.update(cdh_conf_from_commandline)

    # Read the database configuration file if there already is one.
    try:
        db_conf_from_file = get_old_db_details()
        db_conf_from_commandline = {
            'host':     args.db_host     if args.db_host     else None,
            'port':     args.db_port     if args.db_port     else None,
            'database': args.db_database if args.db_database else None,
            'username': args.db_username if args.db_username else None,
            'password': args.db_password if args.db_password else None }
    except IOError:
        # Problem reading old database config file.
        for key in db_conf_from_commandline:
            if db_conf_from_commandline[key] is None:
                cc.log.fatal("No previous database config file found, and missing '" + key +
                             "' parameter.")
        db_conf = db_conf_from_commandline
    else:
        # Take what is on the commandline and attempt to integrate the two.
        for key in db_conf_from_commandline:
            if db_conf_from_commandline[key] is None:
                cc.log.warning("Previous database config file found, but missing '" + key +
                               "' parameter on command line.\n" +
                               "Generated database config may be incorrect.")
        db_conf = db_conf_from_file
        db_conf.update(db_conf_from_file)

    # Handle the db_only option.
    if args.db_only.lower().strip() == 'yes':
        # User wants to just write a new database config and leave CDH config unchanged.
        try:
            test_old_cdh_conf()
        except Exception as e:
            cc.log.warning(e)
            print color_text(e + "\nDid you mean to create a new one?", WARNING)
        else:
            cc.log.warning("Existing cdh.conf file being used.")
            print color_text("Existing cdh.conf file being used.  " +
                             "Did you mean to create a new one?", WARNING)
    else:   # db_only == 'no'
        cc.log.warning("New cdh.conf file will be written.")
        for key in cdh_conf:
            if cdh_conf[key] is None:
                # Sanity check.  We should never get here.
                cc.log.fatal("Missing '" + key + "' parameter for main CDH config.\n" +
                             "Cannot write new file!")
        # Write out CDH file
        cdh_conf_to_write = {
            'fs.root': "hdfs://{0}:{1}/user/{2}".format(cdh_conf.host, cdh_conf.port, cdh_conf.user),
            'titan.load.storage.hostname': '"' + ','.join(yarn_host_names) + '"',
            'titan.load.storage.port': '"' + zookeeper_client_port + '"' }
        create_config(identifier='CDH', prefix='trustedanalytics.atk.engine',
                           confs=cdh_conf_to_write, filename=args.path+'cdh.conf')

    # Write new db.conf regardless of the --db_only parameter.
    create_config(identifier='database',
                  prefix='trustedanalytics.atk.metastore.connection-postgresql',
                  confs=db_conf, filename=args.path+'db.conf')

    set_db_details(db_conf.database, db_conf.username, db_conf.password)

    #TODO: Make sure we are setting up everything for yarn-cluster
    # mode correctly per the document on the Wiki
    # "ATK with Spark on yarn-cluster mode (Serial and Parallel execution"

    print color_text("Intel Analytics is ready for use.", GOOD)


if __name__ == '__main__':
    run(cc.cli.parse(cli()))
