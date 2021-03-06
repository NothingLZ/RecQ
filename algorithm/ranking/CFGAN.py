#coding:utf8
from baseclass.DeepRecommender import DeepRecommender
import numpy as np
from random import randint,choice

try:
    import tensorflow as tf
except ImportError:
    print 'This method can only run on tensorflow!'
    exit(-1)
from tensorflow import set_random_seed
set_random_seed(2)

class CFGAN(DeepRecommender):

    def __init__(self,conf,trainingSet=None,testSet=None,fold='[1]'):
        super(CFGAN, self).__init__(conf,trainingSet,testSet,fold)
        self.negRatio = 0.3
        self.alpha = 1

    def next_batch(self):
        C_u = np.zeros((self.batch_size,self.n))
        N_u = np.zeros((self.batch_size,self.n))

        mask = np.zeros((self.batch_size,self.n)) #e_u + k_u
        userList = self.data.user.keys()
        itemList = self.data.item.keys()
        for n in range(self.batch_size):
            user = choice(userList)
            vec = self.data.row(user)

            ratedItems, values = self.data.userRated(user)
            for item in ratedItems:
                iid = self.data.item[item]
                mask[n][iid]=1
            for i in range(int(self.negRatio*len(ratedItems))):
                ng = choice(itemList)
                while self.data.trainSet_u.has_key(ng):
                    ng = choice(itemList)
                ng = self.data.item[ng]
                mask[n][ng]=1
                N_u[n][ng] = 1

            C_u[n]=vec
        return C_u,mask,N_u

    def initModel(self):
        super(CFGAN, self).initModel()
        G_regularizer = tf.contrib.layers.l2_regularizer(scale=0.001)
        D_regularizer = tf.contrib.layers.l2_regularizer(scale=0.001)
        xavier_init = tf.contrib.layers.xavier_initializer()

        with tf.variable_scope("Generator"):
            # Generator Net
            self.C = tf.placeholder(tf.float32, shape=[None, self.n], name='C')

            G_W1 = tf.get_variable(name='G_W1',initializer=xavier_init([self.n,300]), regularizer=G_regularizer)
            G_b1 = tf.get_variable(name='G_b1',initializer=tf.zeros(shape=[300]), regularizer=G_regularizer)

            G_W2 = tf.get_variable(name='G_W2',initializer=xavier_init([300,200]), regularizer=G_regularizer)
            G_b2 = tf.get_variable(name='G_b2',initializer=tf.zeros(shape=[200]), regularizer=G_regularizer)

            G_W3 = tf.get_variable(initializer=xavier_init([200,self.n]), name='G_W3',regularizer=G_regularizer)
            G_b3 = tf.get_variable(initializer=tf.zeros(shape=[self.n]), name='G_b3',regularizer=G_regularizer)

            theta_G = [G_W1, G_W2, G_W3, G_b1, G_b2, G_b3]

        with tf.variable_scope("Discriminator"):
            # Discriminator Net
            self.X = tf.placeholder(tf.float32, shape=[None, self.n], name='X')

            D_W1 = tf.get_variable(initializer=xavier_init([self.n,300]), name='D_W1',regularizer=D_regularizer)
            D_b1 = tf.get_variable(initializer=tf.zeros(shape=[300]), name='D_b1',regularizer=D_regularizer)

            D_W2 = tf.get_variable(name='D_W2', initializer=xavier_init([300, 200]), regularizer=D_regularizer)
            D_b2 = tf.get_variable(name='D_b2', initializer=tf.zeros(shape=[200]), regularizer=D_regularizer)

            D_W3 = tf.get_variable(initializer=xavier_init([200,1]), name='D_W3',regularizer=D_regularizer)
            D_b3 = tf.get_variable(initializer=tf.zeros(shape=[1]), name='D_b3',regularizer=D_regularizer)

            theta_D = [D_W1, D_W2, D_W3, D_b1, D_b2, D_b3]

        self.mask = tf.placeholder(tf.float32, shape=[None, self.n], name='mask')
        self.N_u = tf.placeholder(tf.float32, shape=[None, self.n], name='mask')

        reg_variables = tf.get_collection(tf.GraphKeys.REGULARIZATION_LOSSES)
        G_reg = tf.contrib.layers.apply_regularization(G_regularizer, reg_variables)
        D_reg = tf.contrib.layers.apply_regularization(D_regularizer, reg_variables)

        #inference
        def generator():
            G_h1 = tf.nn.sigmoid(tf.matmul(self.C, G_W1) + G_b1)
            G_h2 = tf.nn.sigmoid(tf.matmul(G_h1, G_W2) + G_b2)
            r_hat = tf.nn.sigmoid(tf.matmul(G_h2, G_W3) + G_b3)
            fake_data = tf.multiply(r_hat,self.mask)
            return fake_data

        def discriminator(x):
            D_h1 = tf.nn.sigmoid(tf.matmul(x, D_W1) + D_b1)
            D_h2 = tf.nn.sigmoid(tf.matmul(D_h1, D_W2) + D_b2)
            D_output = tf.nn.sigmoid(tf.matmul(D_h2, D_W3) + D_b3)
            return  D_output

        def r_hat():
            G_h1 = tf.nn.sigmoid(tf.matmul(self.C, G_W1) + G_b1)
            G_h2 = tf.nn.sigmoid(tf.matmul(G_h1, G_W2) + G_b2)
            r_hat = tf.nn.sigmoid(tf.matmul(G_h2, G_W3) + G_b3)
            return r_hat

        G_sample = generator()
        self.r_hat = r_hat()
        D_real = discriminator(self.C)
        D_fake = discriminator(G_sample)


        self.D_loss = -tf.reduce_mean(tf.log(D_real) + tf.log(1. - D_fake))+tf.reduce_mean(D_reg)
        self.G_loss = tf.reduce_mean(tf.log(1.-D_fake)+self.alpha*tf.nn.l2_loss(tf.multiply(self.N_u,G_sample)))+tf.reduce_mean(D_reg)

        # Only update D(X)'s parameters, so var_list = theta_D
        self.D_solver = tf.train.AdamOptimizer(self.lRate).minimize(self.D_loss, var_list=theta_D)
        # Only update G(X)'s parameters, so var_list = theta_G
        self.G_solver = tf.train.AdamOptimizer(self.lRate).minimize(self.G_loss, var_list=theta_G)


    def buildModel(self):

        init = tf.global_variables_initializer()
        self.sess.run(init)

        print 'pretraining...'


        print 'training...'
        for epoch in range(self.maxIter):
            G_loss = 0

            C_u, mask, N_u = self.next_batch()
            _, D_loss = self.sess.run([self.D_solver, self.D_loss], feed_dict={self.C: C_u,self.mask:mask,self.N_u:N_u})

            for i in range(3):
                _, G_loss = self.sess.run([self.G_solver, self.G_loss], feed_dict={self.C: C_u,self.mask:mask,self.N_u:N_u})

            #C_u, mask, N_u = self.next_batch()
            print 'iteration:', epoch, 'D_loss:', D_loss, 'G_loss', G_loss



    def predictForRanking(self, u):
        'invoked to rank all the items for the user'
        if self.data.containsUser(u):
            vec = self.data.row(u).reshape(1,self.n)
            u = self.data.user[u]
            res = self.sess.run([self.r_hat], feed_dict={self.C: vec})[0]
            print res[0]
            return res[0]

        else:
            return [self.data.globalMean] * len(self.data.item)



