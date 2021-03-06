#coding:utf8
from baseclass.DeepRecommender import DeepRecommender
import numpy as np
from random import choice,random
from tool import config
try:
    import tensorflow as tf
except ImportError:
    print 'This method can only run on tensorflow!'
    exit(-1)
from tensorflow import set_random_seed
set_random_seed(2)

class CDAE(DeepRecommender):

    def __init__(self,conf,trainingSet=None,testSet=None,fold='[1]'):
        super(CDAE, self).__init__(conf,trainingSet,testSet,fold)

    def encoder(self,x,v):
        layer = tf.nn.sigmoid(tf.matmul(tf.concat([x,v],1), self.weights['encoder'])+self.biases['encoder'])
        #layer = tf.nn.sigmoid(tf.add(tf.matmul(x, self.weights['encoder']), self.biases['encoder']))
        return layer

    def decoder(self,x):
        layer = tf.nn.sigmoid(tf.matmul(x, self.weights['decoder'])+self.biases['decoder'])
        return layer

    def next_batch(self):
        X = np.zeros((self.batch_size,len(self.data.item)))
        uids = []
        evaluated = np.zeros((self.batch_size,len(self.data.item)))>0
        userList = self.data.user.keys()
        itemList = self.data.item.keys()
        for n in range(self.batch_size):
            user = choice(userList)
            uids.append(self.data.user[user])
            vec = self.data.row(user)

            ratedItems, values = self.data.userRated(user)
            for item in ratedItems:
                iid = self.data.item[item]
                evaluated[n][iid]=1
            for i in range(self.negative_sp*len(ratedItems)):
                ng = choice(itemList)
                while self.data.trainSet_u.has_key(ng):
                    ng = choice(itemList)
                ng = self.data.item[ng]
                evaluated[n][ng]=1
            X[n]=vec
        return X,uids,evaluated

    def readConfiguration(self):
        super(CDAE, self).readConfiguration()
        args = config.LineConfig(self.config['CDAE'])
        self.corruption_level = float(args['-co'])
        self.n_hidden = int(args['-nh'])

    def initModel(self):
        super(CDAE, self).initModel()

        self.negative_sp = 5
        initializer = tf.contrib.layers.xavier_initializer()
        self.X = tf.placeholder(tf.float32, [None, self.n])
        self.mask_corruption = tf.placeholder(tf.float32, [None, self.n])
        self.sample = tf.placeholder(tf.float32, [None, self.n])
        #self.zeros = np.zeros((self.batch_size,self.n))
        self.U = tf.Variable(initializer([self.m, self.k]))
        self.U_embed = tf.nn.embedding_lookup(self.U, self.u_idx)



        self.weights = {
            'encoder': tf.Variable(initializer([self.n+self.k, self.n_hidden])),
            'decoder': tf.Variable(initializer([self.n_hidden, self.n])),
        }
        self.biases = {
            'encoder': tf.Variable(initializer([self.n_hidden])),
            'decoder': tf.Variable(initializer([self.n])),
        }

    #def pretrain(self,var,data):

    def buildModel(self):
        self.corrupted_input = tf.multiply(self.X,self.mask_corruption)
        self.encoder_op = self.encoder(self.corrupted_input,self.U_embed)
        self.decoder_op = self.decoder(self.encoder_op)


        self.y_pred = tf.multiply(self.sample,self.decoder_op)
        y_true = tf.multiply(self.sample,self.corrupted_input)
        self.y_pred = tf.maximum(1e-6, self.y_pred)
        # self.cost1 = tf.multiply(self.X, tf.log(self.decoder_op))
        # self.cost2 = tf.multiply((1 - self.X), tf.log(1 - self.decoder_op))
        # self.loss = -1 * tf.multiply(self.X, tf.log(self.decoder_op)) - tf.multiply((1 - self.X), tf.log(1 - self.decoder_op))

        #self.loss = tf.nn.sigmoid_cross_entropy_with_logits(logits=y_pred,labels=y_true)
        self.loss = -tf.multiply(y_true,tf.log(self.y_pred))-tf.multiply((1-y_true),tf.log(1-self.y_pred))


        self.reg_loss = self.regU*(tf.nn.l2_loss(self.weights['encoder'])+tf.nn.l2_loss(self.weights['decoder'])+
                                   tf.nn.l2_loss(self.biases['encoder'])+tf.nn.l2_loss(self.biases['decoder']))

        self.reg_loss = self.reg_loss + self.regU*tf.nn.l2_loss(self.U_embed)
        self.loss = self.loss + self.reg_loss
        self.loss = tf.reduce_mean(self.loss)

        optimizer = tf.train.AdamOptimizer(self.lRate).minimize(self.loss)


        init = tf.global_variables_initializer()
        self.sess.run(init)


        for epoch in range(self.maxIter):

            mask = np.random.binomial(1, self.corruption_level,(self.batch_size, self.n))
            batch_xs,users,sample = self.next_batch()

            _, loss,y = self.sess.run([optimizer, self.loss,self.y_pred], feed_dict={self.X: batch_xs,self.mask_corruption:mask,self.u_idx:users,self.sample:sample})

            print self.foldInfo,"Epoch:", '%04d' % (epoch + 1),"loss=", "{:.9f}".format(loss)
            #print y
            #self.ranking_performance()
        print("Optimization Finished!")



    def predictForRanking(self, u):
        'invoked to rank all the items for the user'
        if self.data.containsUser(u):
            vec = self.data.row(u).reshape((1,len(self.data.item)))
            uid = [self.data.user[u]]
            return self.sess.run(self.decoder_op,feed_dict={self.X:vec,self.mask_corruption:np.ones((1,len(self.data.item))),self.u_idx:uid})[0]
        else:
            return [self.data.globalMean] * len(self.data.item)


