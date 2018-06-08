
import boto3
import json
from .logging import logError, logInfo, logRecycle, logSuccess, logDebug
import uuid
from .globals import CERT_POSTFIX, KEY_POSTFIX

class Thing():

    def __init__(self, config):
        self.config = config
        self.iot = boto3.client('iot', region_name=self.config.Region)
        self.entityName = "thing"

    def dumpKeys(self, name, cert, privkey):
        print('Certificate PEM')
        with open(name+CERT_POSTFIX, 'w') as f:
            f.write(cert)

        print(cert)
        print('PrivateKey')

        with open(name+KEY_POSTFIX, 'w') as f:
            f.write(privkey)
        print(privkey)

    def createThing(self, name, policy):
        res = self.iot.create_thing(thingName=name)
        thingArn = res['thingArn']
        res = self.iot.list_thing_principals(thingName=name)
        principals = res['principals']
        logDebug(principals)
        if not policy in self.config.Policies:
            logError('Missing policy {0} from configuration'.format(policy))
        policyDoc = self.config.Policies[policy]
        
        if len(principals) > 1:
            logError(
                'Thing should only have 1 certificate. Not possible to continue')
            return False
        elif len(principals) == 1:
            certArn = res['principals'][0]
            self._createOrUpdatePolicy(policy, policyDoc)
            logRecycle('Using exisiting thing')
        else:
            res = self.iot.create_keys_and_certificate(setAsActive=True)
            certArn = res['certificateArn']
            logSuccess('Certificate {0}'.format(certArn))
            self.dumpKeys(name, res['certificatePem'], res['keyPair']['PrivateKey'])

            self._createOrUpdatePolicy(policy, policyDoc)

            res = self.iot.attach_principal_policy(
                policyName=policy + "_Policy", principal=certArn)
            logInfo('Attached policy to certificate')
            res = self.iot.attach_thing_principal(
                thingName=name, principal=certArn)
            logInfo('Attached certificate to thing')
        return {'thingArn': thingArn, 'certArn': certArn}


    def getThingDefinition(self, things):
        return [
            {
                "ThingArn": t['thingArn'],
                "SyncShadow":t['syncShadow'],
                "CertificateArn":t['certArn'],
                "Id":str(uuid.uuid4())
            }
            for t in things]

    def _createOrUpdatePolicy(self, policyName, policyDoc):
        policies = dict([(x['policyName'], x['policyArn']) for x in self.iot.list_policies()['policies']])

        if policyName + '_Policy' in policies.keys():
            currentPolicyDoc = self.iot.get_policy(policyName=policyName + '_Policy')['policyDocument']
            #logInfo(currentPolicyDoc)
            if policyDoc == json.loads(currentPolicyDoc):
                logInfo('Policies are identical')
            # Should check if policies are identical
            logRecycle('Policy {0} already exists with arn {1}'.format(
                policyName + '_Policy', policies[policyName + '_Policy']))
        else:
            res = self.iot.create_policy(
                policyName=policyName + "_Policy", policyDocument=json.dumps(policyDoc))
            logSuccess('Created policy {0}'.format(res['policyArn']))
        return policyName