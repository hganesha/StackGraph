const { SNSClient, PublishCommand } = require("@aws-sdk/client-sns");

const client = new SNSClient({});

exports.handler = async (event) => {
  await client.send(new PublishCommand({ Message: event.body, TopicArn: process.env.TOPIC_ARN }));
  return { statusCode: 202 };
};
