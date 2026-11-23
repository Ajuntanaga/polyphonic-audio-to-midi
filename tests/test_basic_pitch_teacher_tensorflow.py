"""Tiny synthetic optimizer contracts; execute only on the GitHub CPU worker."""
import os
import unittest

import numpy as np

from tools.portable_basic_pitch_teacher_adaptation import make_step, training_objective


@unittest.skipUnless(os.environ.get('GITHUB_ACTIONS') == 'true', 'TensorFlow runs on GitHub only')
class TeacherTensorflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tensorflow as tf
        tf.config.set_visible_devices([], 'GPU')
        cls.tf = tf

    def test_teacher_gradient_stopped_and_student_gradient_finite(self):
        tf = self.tf
        note = tf.Variable([.4, .6], dtype=tf.float32)
        onset = tf.Variable([.3, .7], dtype=tf.float32)
        qn = tf.Variable([.2, .8], dtype=tf.float32)
        qo = tf.Variable([.1, .9], dtype=tf.float32)
        with tf.GradientTape() as tape:
            terms = training_objective(tf, tf.constant([0., 1.]),
                dict(note=note, onset=onset), qn, qo)
        gradients = tape.gradient(terms['total'], [note, onset, qn, qo])
        self.assertIsNone(gradients[2])
        self.assertIsNone(gradients[3])
        for gradient in gradients[:2]:
            self.assertTrue(np.isfinite(gradient.numpy()).all())
            self.assertTrue(np.any(gradient.numpy() != 0))

    def test_real_optimizer_step_learns_label_and_restores_onset_teacher(self):
        tf = self.tf
        class TinyModel(tf.Module):
            def __init__(self):
                super().__init__()
                self.note_logit = tf.Variable(0., name='note_logit')
                self.onset_logit = tf.Variable(1., name='onset_logit')

            def __call__(self, signal):
                shape = [tf.shape(signal)[0], 172, 88]
                return dict(note=tf.broadcast_to(tf.sigmoid(self.note_logit), shape),
                            onset=tf.broadcast_to(tf.sigmoid(self.onset_logit), shape))

        model = TinyModel()
        optimizer = tf.keras.optimizers.Adam(learning_rate=.0001, epsilon=1e-7)
        optimizer.build(list(model.trainable_variables))
        step = make_step(model, tf, optimizer)
        teacher = np.full((1, 172, 88), .5, dtype=np.float32)
        teacher.flags.writeable = False
        terms, norm = step(tf.zeros([1, 43844, 1]), tf.ones([1, 172, 88]),
                           tf.convert_to_tensor(teacher), tf.convert_to_tensor(teacher))
        self.assertGreater(float(model.note_logit), 0)
        self.assertLess(float(model.onset_logit), 1)
        self.assertGreater(float(norm), 0)
        self.assertTrue(all(np.isfinite(float(v)) for v in terms.values()))
        self.assertTrue(np.all(teacher == .5))
        self.assertFalse(teacher.flags.writeable)


if __name__ == '__main__':
    unittest.main()
