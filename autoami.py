# Automated AMI Backups
#
# This script will search for all instances having a tag name with "BKUP"
# with value of "TRUE". As soon as we have the instances list, we loop through
# each instance and create an AMI of it. Also, it will look for a "Retention" tag key which
# will be used as a retention policy number in days. If there is no tag with
# that name, it will use a 30 days default value for each AMI.
#
# Also provides an exclusion for an additional tag with a varying deleteon date if needed
#
# After creating the AMI it creates a "DeleteOn" tag on the AMI indicating when
# it will be deleted using the Retention value and another Lambda function

import boto3
import collections
import jmespath
import datetime

ec = boto3.client('ec2')


def lambda_handler(event, context):
    reservations = ec.describe_instances(
        Filters=[
            {'Name': 'tag:BKUP', 'Values': ['TRUE']},
        ]
    ).get(
        'Reservations', []
    )

    found_instances = sum(
        [
                [i for i in r['Instances']]
                for r in reservations], []
    )

    #print "Found %d instances that need backing up" % len(instances)

    ami_ids = []
    instancenames = []
    is_aem = []

    # for every instance that needs to be dealt with:
    for instance in found_instances:
        # clean up our tag name
        name = str(jmespath.search("Tags[?Key=='Name'].Value ", instance)).strip('[]')
        name = str(name).strip("''")
        # add to our list of names
        instancenames.append(name)

        #find which instances are AEM so we can change the retention days dynamically
        if 'AEM' in str(jmespath.search("Tags[?Key=='Application'].Value ", instance)).strip('[]'):
            is_aem.append(True)
        else:
            is_aem.append(False)

        try:
            retention_days = [
                int(t.get('Value')) for t in instance['Tags']
                if t['Key'] == 'Retention'][0]
        except IndexError:
            retention_days = 30
            create_time = datetime.datetime.now()
            create_fmt = create_time.strftime('%Y-%m-%d')

            AMIid = ec.create_image(InstanceId=instance['InstanceId'],
                                    Name=name + "_" + create_time.strftime('%Y-%m-%d_%a'),
                                    Description="Lambda created AMI of instance " + instance['InstanceId'],
                                    NoReboot=True,
                                    DryRun=False)

            ami_ids.append(AMIid['ImageId'])

    for index, ami in enumerate(ami_ids):
        if is_aem[index]:
            delete_date = datetime.date.today() + datetime.timedelta(days=15)
        else:
            delete_date = datetime.date.today() + datetime.timedelta(days=retention_days)

        delete_fmt = delete_date.strftime('%m-%d-%Y')
        ec.create_tags(Resources=[ami],
                       Tags=[
                             {'Key': 'DeleteOn', 'Value': delete_fmt},
                             {'Key': 'Name', 'Value': instancenames[index] + "_" + create_time.strftime('%Y-%m-%d_%a')}
                            ],
                       DryRun=False)