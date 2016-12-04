#!/usr/bin/env python

import sys
import csv

import rospy
from actionlib import SimpleActionClient

from actionlib_msgs.msg import GoalStatus
from rosplan_dispatch_msgs.msg import ActionDispatch, ActionFeedback
from std_msgs.msg import String
from diagnostic_msgs.msg import KeyValue
from bebop_controller.msg import *
from move_base_msgs.msg import MoveBaseAction, MoveBaseGoal
from coordinator.srv import *


class ActionName:
    goto = "goto"
    land = "land"
    takeoff = "takeoff"
    follow = "follow"
    load = "load"
    unload = "unload"


class CoordinatorError(Exception):
     def __init__(self, value):
         self.value = value
     def __str__(self):
         return repr(self.value)


class Action:
    def __init__(self, action_dispatch_msg):
        self.msg = action_dispatch_msg
        self.action_id = action_dispatch_msg.action_id
        self.name = action_dispatch_msg.name

        self.parameters = action_dispatch_msg.parameters

        self.obj = None
        self.wp = None

        for p in self.parameters:
            if p.key == "agent" or p.key == "drone":
                self.obj = p.value
            if p.key == "to":
                self.wp = p.value

        if self.obj == None:
            raise CoordinatorError("No key obj in action dispatch parameter")
        if self.wp == None and self.name == ActionName.goto:
            raise CoordinatorError("No key wp in action dispatch parameter")


class Coordinator:
    def __init__(self, wp_file):
        self.clients = {}

        rospy.init_node('coordinator', anonymous=True, log_level=rospy.INFO)

        rospy.loginfo('/coordinator/__init__/ - Using waypoints from %s', wp_file)

        # Set up Publisher
        self.feedback_pub = rospy.Publisher("/kcl_rosplan/action_feedback", ActionFeedback, queue_size=10)

        #Interface to Turtlebot
        self.clients['turtle_move_ac'] = SimpleActionClient("move_base", MoveBaseAction)

        #Interface to Bebop
        self.clients['bebop_land_ac'] = SimpleActionClient("BebopLandAction", BebopLandAction)
        self.clients['bebop_load_ac'] = SimpleActionClient("BebopLoadAction", BebopLoadAction)
        self.clients['bebop_move_ac'] = SimpleActionClient("BebopMoveBaseAction", BebopMoveBaseAction)
        self.clients['bebop_takeoff_ac'] = SimpleActionClient("BebopTakeOffAction", BebopTakeOffAction)
        self.clients['bebop_unload_ac'] = SimpleActionClient("BebopUnloadAction", BebopUnloadAction)
        self.clients['bebop_follow_ac'] = SimpleActionClient("BebopFollowAction", BebopFollowAction)

        rospy.loginfo('* Coordinator is waiting for action clients')
        for k in self.clients.keys():
          self.clients[k].wait_for_server()

        # Wait for WorldState before accepting any actions
        rospy.loginfo("* Coordinator is waiting for world state update handler")
        waypoint_srv_name = 'world_state/get_waypoint_position'
        rospy.wait_for_service(waypoint_srv_name)
        self.get_waypoint_position = rospy.ServiceProxy(waypoint_srv_name, WaypointPosition)
        srv_name = 'world_state/action_finished'
        rospy.wait_for_service(srv_name)
        self.action_finished_update = rospy.ServiceProxy(srv_name, ActionFinished)

        self.coordinate_frame = rospy.get_param("~coordinate_frame", "map")

        # Interface to ROSplan
        rospy.Subscriber("/kcl_rosplan/action_dispatch", ActionDispatch, self.action_dispatch_callback)


    def action_dispatch_callback(self, msg):
        # Check Action type and call correct functions.
        action = Action(msg)
        rospy.loginfo('/coordinator/action_dispatch_callback obj "%s", action "%s"', action.obj, action.name)

        # Shared actions between action feeder and planner
        if (msg.name == 'goto'):
            self.action_goto(action)
        elif (msg.name == 'takeoff'):
            self.action_takeoff(action)
        elif (msg.name == 'land'):
            self.action_land(action)
        elif (msg.name == 'load'):
            self.action_load(action)
        elif (msg.name == 'unload'):
            self.action_unload(action)
        elif (msg.name == 'follow'):
            self.action_follow(action)
        #Actions only defined by planner
        elif (msg.name == 'pick-up'):
            self.action_load(action)
        elif (msg.name == 'hand-over'):
            self.action_load(action)
        else:
            rospy.loginfo("No action called %s for obj %s", msg.name, msg.obj)


    def _action_feedback_from_state(self, action, state):
        success = (state == GoalStatus.SUCCEEDED)

        # Feedback to rosplan
        feedback_msg = ActionFeedback()
        feedback_msg.action_id = action.action_id
        feedback_msg.status = "action achieved" if success else "action failed"
        self.feedback_pub.publish(feedback_msg)

        # Update world state
        update_request = ActionFinishedRequest(action = action.msg, success = success)
        self.action_finished_update(update_request)


    def action_takeoff(self, action):
        rospy.loginfo('/coordinator/action_takeoff for %s', action.obj)

        action_id = action.action_id
        feedback_msg = ActionFeedback(action_id=action_id, status="action enabled")

        ac = self.clients['bebop_takeoff_ac']

        ac.send_goal(BebopTakeOffGoal())
        ac.wait_for_result()

        self._action_feedback_from_state(action, ac.get_state())


    def action_land(self, action):
        rospy.loginfo('/coordinator/action_land for %s', action.obj)

        action_id = action.action_id
        feedback_msg = ActionFeedback(action_id=action_id, status="action enabled")

        ac = self.clients['bebop_land_ac']

        ac.send_goal(BebopLandGoal())
        ac.wait_for_result()

        self._action_feedback_from_state(action, ac.get_state())


    def action_load(self, action):
        rospy.loginfo('/coordinator/action_load for %s', action.obj)

        action_id = action.action_id
        feedback_msg = ActionFeedback(action_id=action_id, status="action enabled")

        ac = self.clients['bebop_load_ac']

        ac.send_goal(BebopLoadGoal())
        ac.wait_for_result()

        self._action_feedback_from_state(action, ac.get_state())


    def action_unload(self, action):
        rospy.loginfo('/coordinator/action_unload for %s', action.obj)

        action_id = action.action_id
        feedback_msg = ActionFeedback(action_id=action_id, status="action enabled")

        ac = self.clients['bebop_unload_ac']

        ac.send_goal(BebopUnloadGoal())
        ac.wait_for_result()

        self._action_feedback_from_state(action, ac.get_state())


    def action_follow(self, action):
        rospy.loginfo('/coordinator/action_follow for %s', action.obj)

        action_id = action.action_id
        feedback_msg = ActionFeedback(action_id=action_id, status="action enabled")

        ac = self.clients['bebop_follow_ac']

        ac.send_goal(BebopFollowGoal())
        ac.wait_for_result()

        self._action_feedback_from_state(action, ac.get_state())


    def action_goto(self, action):
    	rospy.loginfo('/coordinator/action_goto for %s', action.obj)
        parameters = action.parameters
        action_id = action.action_id
        obj = action.obj
        wp = action.wp

        ac = None
        if obj in rospy.get_param('/available_drones'):
            goal = BebopMoveBaseGoal()
            ac = self.clients['bebop_move_ac']
        elif obj in rospy.get_param('/available_turtlebots'):
            goal = MoveBaseGoal()
            ac = self.clients['turtle_move_ac']
        if ac == None:
            raise CoordinatorError("No action client exist for obj %s" % obj)

        if not ac.wait_for_server(timeout=rospy.Duration(10)):
            rospy.loginfo("server timeout")

        #Get waypoint position from world state node
        p_rsp = self.get_waypoint_position(wp = wp)
        if not p_rsp.valid:
            raise CoordinatorError("No valid position for waypoint %s" % wp)

        goal.target_pose.header.frame_id = self.coordinate_frame
        goal.target_pose.header.stamp = rospy.Time.now()
        goal.target_pose.pose.position.x = p_rsp.x
        goal.target_pose.pose.position.y = p_rsp.y
        goal.target_pose.pose.orientation.w = 1

        # Notify action dispatcher of status
        feedback_msg = ActionFeedback(action_id = action_id, status = "action enabled")
        self.feedback_pub.publish(feedback_msg)

        ac.send_goal(goal)
        ac.wait_for_result()

        self._action_feedback_from_state(action, ac.get_state())


    def test_actions(self):
        dispatch_msg = ActionDispatch()
        dispatch_msg.name = "goto"
        dispatch_msg.parameters = [KeyValue('obj','turtle'), KeyValue('wp','wp1')]
        tmp_pub = rospy.Publisher("/kcl_rosplan/action_dispatch", ActionDispatch, queue_size=1)
        rospy.sleep(0.1)
        tmp_pub.publish(dispatch_msg)
        rospy.logdebug('coordinator:test_actions')


    def spin(self):
        rospy.spin()


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("usage: coordinator.py waypoint_file")
    else:
        coordinator = Coordinator(sys.argv[1])
        #rospy.sleep(0.1)
        #coordinator.test_actions()
        coordinator.spin()
