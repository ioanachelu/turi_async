import numpy as np
import tensorflow as tf

FLAGS = tf.app.flags.FLAGS


class GACNetwork:
    def __init__(self, nb_actions):
        self.nb_actions = nb_actions

        self.graph = tf.Graph()
        with self.graph.as_default() as g:
            with tf.device('gpu:0'):
                self.summaries = tf.get_collection(tf.GraphKeys.SUMMARIES)
                self.global_step = tf.Variable(0, dtype=tf.int32, name='global_episodes', trainable=False)
                self.increment_global_step = self.global_step.assign_add(1)
                self.inputs = tf.placeholder(
                    shape=[None, FLAGS.resized_height, FLAGS.resized_width, FLAGS.agent_history_length],
                    dtype=tf.float32,
                    name="Input")
                self.discounted_returns = tf.placeholder(tf.float32, [None], name='Return')
                self.actions = tf.placeholder(shape=[None], dtype=tf.int32)
                self.actions_onehot = tf.one_hot(self.actions, nb_actions, dtype=tf.float32)

                self.conv1 = tf.contrib.layers.conv2d(
                    self.inputs, 16, 5, 2, activation_fn=tf.nn.relu, scope="conv1")
                self.conv2 = tf.contrib.layers.conv2d(
                    self.conv1, 32, 5, 2, padding="VALID", activation_fn=tf.nn.relu, scope="conv2")

                self.summaries.append(tf.summary.histogram("conv1", self.conv1))
                self.summaries.append(tf.summary.histogram("conv2", self.conv2))

                self.hidden = tf.contrib.layers.fully_connected(
                    inputs=tf.contrib.layers.flatten(self.conv2),
                    num_outputs=32,
                    scope="fc1")
                self.summaries.append(tf.summary.histogram("hidden", self.hidden))

                self.value = tf.squeeze(tf.contrib.layers.fully_connected(
                    inputs=self.hidden,
                    num_outputs=1,
                    activation_fn=None, scope="value"), axis=[1])
                self.summaries.append(tf.summary.histogram("value_function", self.value))

                self.policy = tf.contrib.layers.fully_connected(self.hidden, self.nb_actions, activation_fn=None,
                                                                scope="policy")
                self.policy = tf.nn.softmax(self.policy, name="policy") + 1e-8
                self.summaries.append(tf.summary.histogram("value_function", self.policy))

                self.responsible_outputs = tf.reduce_sum(self.policy * self.actions_onehot, [1])

                # Loss functions
                self.value_loss = tf.reduce_sum(tf.square(self.discounted_returns - self.value), name="value_loss")
                self.summaries.append(tf.summary.scalar('Losses/Value Loss', self.value_loss))

                self.entropy = - tf.reduce_sum(self.policy * tf.log(self.policy), name="entropy")
                self.summaries.append(tf.summary.scalar('Losses/Entropy', self.entropy))

                self.policy_loss = -tf.reduce_sum(
                    tf.log(self.responsible_outputs) * (self.discounted_returns - tf.stop_gradient(self.value)), name="policy_loss")
                self.summaries.append(tf.summary.scalar('Losses/Policy Loss', self.policy_loss))

                self.loss = FLAGS.beta_v * self.value_loss + self.policy_loss - self.entropy * FLAGS.beta_e
                self.summaries.append(tf.summary.scalar('Losses/Total Loss', self.policy_loss))

                self.optimizer = tf.train.RMSPropOptimizer(FLAGS.lr, 0.99, 0.0, 0.1)
                self.gradients = self.optimizer.compute_gradients(self.loss)
                self.grad_clipped = [(tf.clip_by_average_norm(g, FLAGS.gradient_clip_value), v) for g, v in
                                     self.gradients]
                self.apply_grads = self.optimizer.apply_gradients(self.grad_clipped)

                self.sess = tf.Session(
                    graph=self.graph,
                    config=tf.ConfigProto(
                        allow_soft_placement=True,
                        log_device_placement=False,
                        gpu_options=tf.GPUOptions(allow_growth=True)))
                saver = tf.train.Saver(max_to_keep=5)
                
                self.summary_op = tf.summary.merge(self.summaries)
                self.log_writer = tf.summary.FileWriter(FLAGS.summaries_dir, self.sess.graph)


                if FLAGS.resume:
                    ckpt = tf.train.get_checkpoint_state(FLAGS.checkpoint_dir)
                    print("Loading Model from {}".format(ckpt.model_checkpoint_path))
                    saver.restore(self.sess, ckpt.model_checkpoint_path)
                else:
                    self.sess.run(tf.global_variables_initializer())

    def increment_global_step(self):
        self.sess.run(self.increment_global_step)

    def log(self, rollout):
        rollout = np.array(rollout)
        observations = rollout[:, 0]
        actions = rollout[:, 1]
        pis = rollout[:, 2]
        rewards = rollout[:, 3]
        next_observations = rollout[:, 4]
        values = rollout[:, 5]
        discounted_returns = rollout[: 6]

        feed_dict = {self.inputs: np.stack(observations, axis=0),
                     self.discounted_returns: discounted_returns,
                     self.actions: actions}
        step, summary = self.sess.run([self.global_step, self.summary_op], feed_dict=feed_dict)
        self.log_writer.add_summary(summary, step)

    def predict(self, s):
        feed_dict = {self.inputs: s}

        pi, v = self.sess.run(
            [self.policy, self.value],
            feed_dict=feed_dict)
        return pi, v

    def train(self, rollout, trainer_id):
        rollout = np.array(rollout)
        observations = rollout[:, 0]
        actions = rollout[:, 1]
        pis = rollout[:, 2]
        rewards = rollout[:, 3]
        next_observations = rollout[:, 4]
        values = rollout[:, 5]
        discounted_returns = rollout[: 6]

        feed_dict = {self.inputs: np.stack(observations, axis=0),
                     self.discounted_returns: discounted_returns,
                     self.actions: actions}

        self.sess.run(self.apply_grads, feed_dict=feed_dict)

    def get_global_step(self):
        step = self.sess.run(self.global_step)
        return step





