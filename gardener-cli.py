#!/usr/local/bin/python
import json
import boto3

import uuid
import re
import sys
import argparse
from collections import OrderedDict
from gardener.utils import jsonPP
from gardener.logging import logError, logInfo, logRecycle, logSuccess, logDebug
from gardener.globals import CERT_POSTFIX, KEY_POSTFIX
from gardener.gardener import Gardener
from gardener.config import Config

gg_client = boto3.client('greengrass')

def getLatestDeploymentStatus(groupName):
    res = gg_client.list_groups()
    group = [g for g in res['Groups'] if g['Name'] == groupName]
    if len(group) == 0:
        logError("No groups matching {0}".format(groupName))
        return False
    res = gg_client.list_deployments(GroupId=group[0]['Id'])
    deployments = res['Deployments']
    if len(deployments) == 0:
        logError("No deployments found for group {0}".format(groupName))
        return False
    deployments = sorted(deployments, key=lambda x: x["CreatedAt"], reverse=True)
    deploymentId = deployments[0]['Id']
    res = gg_client.get_deployment_status(DeploymentId = deploymentId, GroupId=group[0]['Id'])
    print("Latest deployment for group {0} is {1}".format(groupName, res['DeploymentStatus']))

def getCurrentConfiguration(groupId=None):
    _regex = '.*{0}/(.*)/versions/(.*)'
    _name = r'(\w+)DefinitionVersionArn'
    func = {
        'cores': lambda a, b : gg_client.get_core_definition_version(CoreDefinitionId = a, CoreDefinitionVersionId = b),
        'devices': lambda a, b : gg_client.get_device_definition_version(DeviceDefinitionId = a, DeviceDefinitionVersionId = b),
        'functions': lambda a, b : gg_client.get_function_definition_version(FunctionDefinitionId = a, FunctionDefinitionVersionId = b),
        'logg_client.rs': lambda a, b : gg_client.get_logger_definition_version(LoggerDefinitionId = a, LoggerDefinitionVersionId = b),
        'subscriptions': lambda a, b : gg_client.get_subscription_definition_version(SubscriptionDefinitionId = a, SubscriptionDefinitionVersionId = b)
    }
    groups = gg_client.list_groups()['Groups']
    if groupId is None:
        jsonPP(groups)
        return
    groupVersions = gg_client.list_group_versions(GroupId = groupId)['Versions']
    latestGroupVersion = groupVersions[0]
    groupDefinition = gg_client.get_group_version(GroupId = groupId, GroupVersionId = latestGroupVersion['Version'])['Definition']
    jsonPP(groupDefinition)
    for d in groupDefinition.keys():    
        _entity = re.match(_name, d)[1].lower()+'s'
        m = re.match(_regex.format(_entity), groupDefinition[d])
        jsonPP(func[_entity](m[1],m[2])['Definition'])
    return


def cleanUpAll():
    groupIds = [x['Id'] for x in gg_client.list_groups()['DefinitionInformationDefinition']]
    coreDefinitionIds = [x['Id'] for x in gg_client.list_core_definitions()['DefinitionInformationDefinition']]
    deviceDefinitionIds = [x['Id'] for x in gg_client.list_device_definitions()['DefinitionInformationDefinition']]
    lambdaDefinitionIds = [x['Id'] for x in gg_client.list_lambda_definitions()['DefinitionInformationDefinition']]
    subscriptionDefinitionIds = [x['Id'] for x in gg_client.list_subscription_definitions()['DefinitionInformationDefinition']]
    loggerDefinitionIds = [x['Id'] for x in gg_client.list_logger.definitions()['DefinitionInformationDefinition']]
    print('Cleaning up groups...')
    for x in groupIds:
        try:
            print(x)
            gg_client.delete_group(GroupId=x)
        except:
            print('Unable to delete')
    print('Cleaning up cores...')
    for x in coreDefinitionIds:
        try:
            print(x)
            gg_client.delete_core_definition(CoreId=x)
        except:
            print('Unable to delete')
    print('Cleaning up devices...')
    for x in deviceDefinitionIds:
        try:
            print(x)
            gg_client.delete_device_definition(DeviceId=x)
        except:
            print('Unable to delete')
    print('Cleaning up lambdas...')
    for x in lambdaDefinitionIds:
        try:
            print(x)
            gg_client.delete_lambda_definition(LambdaId=x)
        except:
            print('Unable to delete')
    print('Cleaning up subscriptions...')
    for x in subscriptionDefinitionIds:
        try:
            print(x)
            gg_client.delete_subscription_definition(SubscritpionId=x)
        except:
            print('Unable to delete')
    print('Cleaning up loggers...')
    for x in loggerDefinitionIds:
        try:
            print(x)
            gg_client.delete_loggers_definition(LoggerId=x)
        except:
            print('Unable to delete')

    
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Greengrass Gardener')
    parser.add_argument('--config')
    subparsers = parser.add_subparsers(help='sub-command help', dest='subparser_name')

    parser_deploy = subparsers.add_parser('deploy', help='deploy help')
    parser_deploy.add_argument('--config')
    parser_ls = subparsers.add_parser('listGroups', help='listGroups help')
    parser_group = subparsers.add_parser('describeGroup', help='describeGroup help')
    parser_group.add_argument('--id')

    args = parser.parse_args()
    if args.config:
        gg = Gardener(args.config)
    else:
        gg = Gardener()
    if args.subparser_name == 'deploy': 
        print (gg.createGreengrass())
    elif args.subparser_name == 'listGroups':
        getCurrentConfiguration()
    elif args.subparser_name == 'describeGroup':
        getCurrentConfiguration(args.id)

        
    