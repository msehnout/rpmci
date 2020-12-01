import json
from typing import Dict, Any

from jsonschema import validate, draft7_format_checker

CONFIGURATION = {
    "type": "object",
    "properties": {
        "target": {
            "type": "object"
        },
        "steering": {
            "type": "object"
        },
        "rpm_repo": {
            "type": "object"
        },
        "credentials": {
            "type": "object"
        },
    },
    "required": ["target"],
    "additionalProperties": False
}

MACHINE = {
    "type": "object",
    "properties": {
        "virtualization": {"type": "object"},
        "rpm": {"type": "string"},
        "invoke": {
            "type": "array",
            "items": {
                "type": "string"
            }
        }
    },
    "required": ["virtualization"],
    "additionalProperties": False
}

VIRTUALIZATION = {
    "type": "object",
    "properties": {
        "type": {
            "type": "string",
            "enum": ["docker", "ec2", "qemu"]
        },
        "ec2": {
            "type": "object",
            "properties": {
                "image_id": {"type": "string"}  # ,
                # "instance_type": {"type": "string"}
            },
            "additionalProperties": False,
            "minProperties": 1
        },
        "docker": {
            "type": "object",
            "properties": {
                "image": {"type": "string"},
                "arguments": {"type": "string"},
                "privileged": {"type": "boolean"}
            }
        },
        "qemu": {
            "type": "object",
            "properties": {
                "image": {"type": "string"},
                "ssh_port": {"type": "number"}
            },
            "additionalProperties": False,
            "minProperties": 2
        },
    },
    "required": ["type"],
    "additionalProperties": False
}

CREDENTIALS = {
    "type": "object",
    "properties": {
        "aws": {"type": "object"}
    },
    "additionalProperties": False
}

AWS_CREDENTIALS = {
    "type": "object",
    "properties": {
        "access_key_id": {"type": "string"},
        "secret_access_key": {"type": "string"},
        "region_name": {"type": "string"}
    },
    "additionalProperties": False
}

RPM_REPO = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "type": "object",
    "properties": {
        "provider": {
            "type": "string",
            "enum": ["existing_url", "local_http"]
        },
        "local_http": {
            "type": "object",
            "properties": {
                "ip": {
                    "type": "string",
                    "format": "ipv4"
                },
                "port": {"type": "number"}
            },
            "required": ["ip", "port"]
        },
        "dir_with_rpms": {"type": "string"},
        "existing_url": {
            "type": "object",
            "properties": {
                "baseurl": {
                    "type": "string",
                    "format": "uri"
                }
            },
            "required": ["baseurl"]
        }
    },
    "required": ["provider"],
    "additionalProperties": False
}


class Conf:
    """RPMCI configuration"""

    def __init__(self, options):
        self.options = options

    @staticmethod
    def _validate(data: Dict[Any, Any]):
        draft7 = draft7_format_checker

        # Mandatory parameters
        validate(data, CONFIGURATION, format_checker=draft7)
        validate(data["target"], MACHINE, format_checker=draft7)
        validate(data["target"]["virtualization"], VIRTUALIZATION, format_checker=draft7)

        # Optional parameters
        if "steering" in data:
            validate(data["steering"], MACHINE, format_checker=draft7)
            validate(data["steering"]["virtualization"], VIRTUALIZATION, format_checker=draft7)

        if "credentials" in data:
            validate(data["credentials"], CREDENTIALS, format_checker=draft7)
            if "aws" in data["credentials"]:
                validate(data["credentials"]["aws"], AWS_CREDENTIALS, format_checker=draft7)

        if "rpm_repo" in data:
            validate(data["rpm_repo"], RPM_REPO, format_checker=draft7)

    @classmethod
    def load(cls, filp):
        """Parse configuration from a file pointer."""
        data = json.load(filp)
        cls._validate(data)
        return cls(data)

    @classmethod
    def loads(cls, configuration: str):
        """Parse configuration from a string."""
        data = json.loads(configuration)
        cls._validate(data)
        return cls(data)


AWS_EXAMPLE = {
    "target": {
        "virtualization": {
            "type": "ec2",
            "ec2": {
                "image_id": "ami-123456789"  # ,
                # "instance_type": "t2.small"
            }
        },
        "rpm": "osbuild-composer-tests",
        "invoke": [
            "/usr/libexec/tests/osbuild-composer/api.sh",
            "/usr/libexec/tests/osbuild-composer/base_tests.sh"
        ]
    },
    "rpm_repo": {
        "provider": "existing_url",
        "existing_url": {
            "baseurl": "http://osbuild-composer-repos.s3-website.us-east-2.amazonaws.com/osbuild-composer/fedora-33/x86_64/207080024408be5698669058ef49d265fbd723b6/"
        }
    },
    "credentials": {
        "aws": {
            "access_key_id": "MYSUPERSECRETACCESSKEYID",
            "secret_access_key": "MYSUPERSECRETACCESSKEY",
            "region_name": "xx-region-1"
        }
    }
}

QEMU_EXAMPLE = {
    "target": {
        "virtualization": {
            "type": "qemu",
            "qemu": {
                "image": "/home/nonsuperuser/fedora-33.qcow2",
                "ssh_port": 2223
            }
        },
        "rpm": "osbuild-composer-tests",
        "invoke": [
            "/usr/libexec/tests/osbuild-composer/api.sh",
            "/usr/libexec/tests/osbuild-composer/base_tests.sh"
        ]
    },
    "rpm_repo": {
        "provider": "local_http",
        "dir_with_rpms": "/home/nonsuperuser/rpms/",
        "local_http": {
            "ip": "10.0.2.2",
            "port": 8000
        }
    }
}


def test_aws_conf_validation():
    example = AWS_EXAMPLE
    Conf.loads(json.dumps(example))


def test_qemu_conf_validation():
    example = QEMU_EXAMPLE
    Conf.loads(json.dumps(example))