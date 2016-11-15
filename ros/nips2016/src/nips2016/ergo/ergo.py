import sys
import os
import rospy
import json
import pygame
import pygame.display
from nips2016.srv import *
from geometry_msgs.msg import PoseStamped
from sensor_msgs.msg import Joy
from poppy.creatures import PoppyErgoJr
from rospkg import RosPack
from os.path import join

os.environ["SDL_VIDEODRIVER"] = "dummy"
try:
    pygame.display.init()
except pygame.error:
    raise pygame.error("Can't connect to the console, from ssh enable -X forwarding")
pygame.joystick.init()


class Ergo(object):
    def __init__(self):
        self.rospack = RosPack()
        with open(join(self.rospack.get_path('nips2016'), 'config', 'ergo.json')) as f:
            self.params = json.load(f)
        self.rate = rospy.Rate(self.params['publish_rate'])
        self.eef_pub = rospy.Publisher('/nips2016/ergo/end_effector_pose', PoseStamped, queue_size=1)
        self.joy_pub = rospy.Publisher('/nips2016/ergo/joysticks/1', Joy, queue_size=1)
        self.joy_pub2 = rospy.Publisher('/nips2016/ergo/joysticks/2', Joy, queue_size=1)
        self.srv_reset = rospy.Service('/nips2016/ergo/reset', Reset, self._cb_reset)
        self.ergo = None
        self.limits = []
        
        if pygame.joystick.get_count() < 2:
            rospy.logerr("Ergo: Expecting 2 joysticks but found only {}, exiting".format(pygame.joystick.get_count()))
            sys.exit(0)
        else:
            self.joystick = pygame.joystick.Joystick(0)
            self.joystick2 = pygame.joystick.Joystick(0)
            self.joystick.init()
            self.joystick2.init()
            rospy.loginfo('Initialized Joystick 1: {}'.format(self.joystick.get_name()))
            rospy.loginfo('Initialized Joystick 2: {}'.format(self.joystick2.get_name()))

    def go_to_start(self):
        self.go_to([0.0, -15.4, 35.34, -8.06, -15.69, 71.99], 1)

    def go_to_extended(self):
        extended = {'m2': 60, 'm3': -37, 'm4': 0, 'm5': -50, 'm6': 96}
        self.ergo.goto_position(extended, 0.5)

    def go_to_rest(self):
        rest = {'m2': -26, 'm3': 59, 'm4': 0, 'm5': -30, 'm6': 78}
        self.ergo.goto_position(rest, 0.5)

    def go_to(self, motors, duration):
        self.ergo.goto_position(dict(zip(['m1', 'm2', 'm3', 'm4', 'm5', 'm6'], motors)), duration)
        rospy.sleep(duration)

    def run(self, dummy=False):
        self.ergo = PoppyErgoJr(use_http=True, simulator='poppy-simu' if dummy else None, camera='dummy')
        self.limits = [self.ergo.config['motors'][motor]['angle_limit'] for motor in ['m1', 'm2', 'm3', 'm4', 'm5', 'm6']]
        self.ergo.compliant = False
        self.go_to_start()
        while not rospy.is_shutdown():
            pygame.event.get()
            x = self.joystick.get_axis(0)
            y = self.joystick.get_axis(1)
            self.servo_robot(y, x)
            self.publish_eef()

            # Publishers
            self.publish_joy(x, y, 1)
            x = self.joystick2.get_axis(0)
            y = self.joystick2.get_axis(1)
            self.publish_joy(x, y, 2)
            self.rate.sleep()

    def servo_axis_rotation(self, x):
        self.servo_axis(x, 0)

    def servo_axis_elongation(self, x):
        if x > 0.5:
            self.go_to_extended()
        else:
            self.go_to_rest()

    def servo_axis(self, x, id):
        p = self.ergo.motors[id].goal_position
        new_x = p + self.params['speed']*x
        if self.limits[id][0] < new_x < self.limits[id][1]:
            self.ergo.motors[id].goto_position(new_x, 0.1)

    def servo_robot(self, x, y):
        self.servo_axis_rotation(-x)
        self.servo_axis_elongation(y)

    def publish_eef(self):
        pose = PoseStamped()
        eef_pose = self.ergo.chain.end_effector
        pose.header.stamp = rospy.Time.now()
        pose.pose.position.x = eef_pose[0]
        pose.pose.position.y = eef_pose[1]
        pose.pose.position.z = eef_pose[2]
        self.eef_pub.publish(pose)

    def publish_joy(self, x, y, id):
        joy = Joy()
        joy.header.stamp = rospy.Time.now()
        joy.axes.append(x)
        joy.axes.append(y)
        if id == 1:
            self.joy_pub.publish(joy)
        else:
            self.joy_pub2.publish(joy)


    def _cb_reset(self, request):
        self.go_to_start()
        return ResetResponse()

