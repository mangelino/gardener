class Config:
    def __init__(self, dictionary):
        for k,v in dictionary.items():
            setattr(self, k, v)

config = Config(
    {
        'Core': 'GGC_Thing',
        'Group': 'GGStoryLine',
        'Things': [
            {
                'id': 'robotarm',
                'name': 'RobotArm_Thing',
                'syncShadow': True
            },
            {
                'id': 'switch',
                'name': 'Switch_Thing',
                'syncShadow': False
            }
        ],
        'Lambdas': [
            {
                'id': 'uptime',
                'arn': 'arn:aws:lambda:us-west-2:416075262792:function:uptimeLambda:1'
            },
            {
                'id': 'message',
                'arn': 'arn:aws:lambda:us-west-2:416075262792:function:messageLambda:1'
            }
        ],
        'Routes': [
                {
                    "Source": "GGShadowService",
                    "Subject": "shadow:switch:/update/rejected",
                    "Target": "thing:switch"
                },
                {
                    "Source": "thing:robotarm",
                    "Subject": "/topic/state",
                    "Target": "lambda:uptime"
                },
                {
                    "Source": "lambda:uptime",
                    "Subject": "/topic/metering",
                    "Target": "cloud"
                },
                {
                    "Source": "thing:switch",
                    "Subject": "shadow:robotarm:/update",
                    "Target": "GGShadowService"
                },
                {
                    "Source": "thing:robotarm",
                    "Subject": "shadow:robotarm:/update",
                    "Target": "GGShadowService"
                },
                {
                    "Source": "lambda:message",
                    "Subject": "shadow:robotarm:/update",
                    "Target": "GGShadowService"
                },
                {
                    "Source": "GGShadowService",
                    "Subject": "shadow:robotarm:/update/delta",
                    "Target": "thing:robotarm"
                },
                {
                    "Source": "GGShadowService",
                    "Subject": "shadow:switch:/update/accepted",
                    "Target": "thing:switch"
                },
                {
                    "Source": "cloud",
                    "Subject": "/topic/update",
                    "Target": "lambda:message"
                },
                {
                    "Source": "GGShadowService",
                    "Subject": "shadow:robotarm:/update/rejected",
                    "Target": "thing:robotarm"
                },
                {
                    "Source": "GGShadowService",
                    "Subject": "shadow:robotarm:/update/delta",
                    "Target": "thing:robotarm"
                },
                {
                    "Source": "GGShadowService",
                    "Subject": "shadow:robotarm:update/accepted",
                    "Target": "GGShadowSyncManager"
                }
        ]
    }
)

