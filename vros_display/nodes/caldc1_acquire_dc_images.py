#!/usr/bin/env python

# standard Python imports
import argparse
import Image as PIL
import numpy as np
import time, tempfile, os, pickle
import Queue
import scipy
import tempfile
import json

# ROS imports
import roslib; roslib.load_manifest('vros_display')
import rospy
from sensor_msgs.msg import Image

# local vros_display imports
import vros_display.srv
import display_client
from graycode import graycode_str, graycode_arange
import mahotas.polygon

import math

# constants
D2R = math.pi/180.0
R2D = 180.0/math.pi

X_AX=0
Y_AX=1

NCHAN=4

class CameraHandler(object):
    def __init__(self,topic_prefix=''):
        self.topic_prefix=topic_prefix
        rospy.Subscriber( '%s/image_raw'%self.topic_prefix, Image,
                          self.get_image_callback)
        self.pipeline_max_latency = 0.15 # 150 msec
        self.last_image = None
        self.im_queue = None
    def set_im_queue(self,q):
        self.im_queue = q
    def get_image_callback(self,msg):
        if self.im_queue is None:
            return
        self.im_queue.put((self.topic_prefix,msg))

class Runner(object):
    def __init__(self,cam_handlers):
        self.cam_handlers = cam_handlers

        max_cam_latency = max( [ch.pipeline_max_latency for ch in self.cam_handlers ])
        display_pipeline_max_latency = 0.2 # 200 msec
        self.wait_duration = max_cam_latency + display_pipeline_max_latency
        self.im_queue = Queue.Queue()
        for ch in self.cam_handlers:
            ch.set_im_queue(self.im_queue)

    def get_images(self,n_per_camera=1):
        self.clear_queue()
        tstart = time.time()
        self.cycle_duration( self.wait_duration )
        t_earliest = tstart + self.wait_duration
        self.clear_queue()
        result = {}
        for ch in self.cam_handlers:
            result[ch.topic_prefix] = []
        while not self._is_done(result,n_per_camera):
            topic_prefix, msg = self.im_queue.get(1,10.0) # block, 10 second timeout
            t_image = msg.header.stamp.to_sec()
            if abs(t_image-t_earliest) > 10.0:
                raise ValueError('image timestamps more than 10 seconds different')
            if t_image < t_earliest:
                # image too old
                continue
            result[topic_prefix].append( msg )
        return result

    def cycle_duration( self, dur ):
        tstart = time.time()
        while (time.time() - tstart) < dur:
            time.sleep(0.05) # wait 50 msec

    def clear_queue(self):
        q = self.im_queue
        while 1:
            try:
                q.get_nowait()
            except Queue.Empty:
                break

    def _is_done(self,rdict,n_per_camera):
        done=True
        for topic_prefix in rdict.keys():
            if len(rdict[topic_prefix]) < n_per_camera:
                done=False
                break
        return done

def set_pixels( display_server, arr ):
    fname = tempfile.mktemp('.png')
    scipy.misc.imsave(fname,arr)
    try:
        image = vros_display.msg.VROSCompressedImage()
        image.format = os.path.splitext(fname)[-1]
        image.data = open(fname).read()
    finally:
        os.unlink(fname)

    # send image to server
    blit_compressed_image_proxy = rospy.ServiceProxy(display_server.get_fullname('blit_compressed_image'),
                                                     vros_display.srv.BlitCompressedImage)
    blit_compressed_image_proxy(image)

def get_mask(verts, width, height ):
    pts = [ (int(y),int(x)) for (x,y) in verts]
    arr = np.zeros( (height, width, NCHAN), dtype=np.uint8)
    mahotas.polygon.fill_polygon(pts, arr[:,:,0])
    arr[:,:,1] = arr[:,:,0]
    arr[:,:,2] = arr[:,:,0]
    arr[:,:,3] = 1
    return arr

def localize_display( topic_prefixes=None, physical_display_id=None, virtual_display_id=None, save_pngs=False ):
    assert len(topic_prefixes)>=1
    print 'topic_prefixes',topic_prefixes

    if 1:
        if physical_display_id is None:
            physical_displays = rospy.get_param('/physical_displays',{})
            if len(physical_displays) != 1:
                raise ValueError('when no physical display ID is specified, only one physical display may be present')
            physical_display_id = physical_displays.keys()[0]
        physical_display = physical_displays[physical_display_id]
        print 'physical_display',physical_display

        # get virtual_display and physical_display parameters
        virtual_displays = rospy.get_param('/virtual_displays/'+physical_display_id,{})
        print 'available virtual_displays',virtual_displays.keys()

    if virtual_display_id is not None:
        if virtual_display_id not in virtual_displays:
            raise ValueError('could not find virtual display with id "%s"'%(virtual_display_id,))

        virtual_display = json.loads(virtual_displays[virtual_display_id]['virtual_display_config_json_string'])
        print 'virtual_display',virtual_display

        viewport_verts=virtual_display['viewport']
        viewport_mask = get_mask( viewport_verts, physical_display['width'], physical_display['height'] )
    else:
        # no virtual display specified -- use entire display
        viewport_mask = np.ones( ( physical_display['height'], physical_display['width'], NCHAN), dtype=np.uint8 )
        print 'no virtual display specified -- using entire display'

    print 'physical_display_id',physical_display_id
    print 'virtual_display_id',virtual_display_id

    rospy.init_node('localize_display', anonymous=True)
    cam_handlers = [CameraHandler(prefix) for prefix in topic_prefixes]

    display_server = display_client.DisplayServerProxy()
    display_server.enter_standby_mode()
    display_server.set_mode('display2d')
    display_info = display_server.get_display_info()

    width = display_info['width']
    height = display_info['height']

    assert width==physical_display['width']
    assert height==physical_display['height']

    runner = Runner(cam_handlers)
    runner.clear_queue()
    runner.cycle_duration(1.0) # give panda a chance to startup...
    runner.clear_queue()

    binary_coding='natural'
    assert binary_coding in ('gray','natural')

    if 1:
        result_images = []
        for axis in [X_AX,Y_AX]:
            arr = np.zeros((height,width,NCHAN),dtype=np.uint8)
            arr[:,:,3]=255
            if binary_coding=='natural':
                if axis==X_AX:
                    vals = np.arange(width, dtype=np.uint16)
                else:
                    vals = np.arange(height, dtype=np.uint16)
            elif binary_coding=='gray':
                if axis==X_AX:
                    vals = graycode_arange(width, dtype=np.uint16)
                else:
                    vals = graycode_arange(height, dtype=np.uint16)
            n_line_images = 30
            bitnos = range(-3,13) + list( 100+np.arange(n_line_images) )
            for bitno in bitnos:
                for flip in [0,1]:
                    if bitno==-3:
                        if flip==0: # invalid
                            continue
                        # all black for bitno -3
                        arr[:,:,:3]=0
                    elif bitno==-2:
                        if flip==0: # invalid
                            continue
                        # all white for bitno -2
                        arr[:,:,:3]=255
                    elif bitno==-1:
                        if flip==0: # invalid
                            continue
                        # all gray for bitno -1
                        arr[:,:,:3]=127
                    elif bitno < 100:
                        mask = 1 << bitno
                        tmp1 = np.bitwise_and(vals,mask)
                        bits = tmp1==0
                        if flip:
                            bits = ~bits
                        bits = 255*bits
                        for chan in range(3):
                            if axis==X_AX:
                                ovals_len = height
                            else:
                                ovals_len = width
                            for oval in range(ovals_len):
                                if axis==X_AX:
                                    arr[oval,:,chan] = bits
                                else:
                                    arr[:,oval,chan] = bits
                    else:
                        if flip==0: # invalid
                            continue
                        modval = bitno-100
                        if axis==X_AX:
                            vals2 = np.arange(width, dtype=np.uint16) % n_line_images
                        else:
                            vals2 = np.arange(height, dtype=np.uint16) % n_line_images

                        bits = vals2==modval
                        if not flip:
                            bits = ~bits
                        bits = 255*bits
                        for chan in range(3):
                            if axis==X_AX:
                                ovals_len = height
                            else:
                                ovals_len = width
                            for oval in range(ovals_len):
                                if axis==X_AX:
                                    arr[oval,:,chan] = bits
                                else:
                                    arr[:,oval,chan] = bits

                    arr = arr*viewport_mask
                    set_pixels(display_server,arr)
                    n_per_camera=10
                    print 'getting images for bitno %d'%bitno
                    imdict = runner.get_images(n_per_camera=n_per_camera)

                    if 0:
                        # don't average images at this stage, just save all images
                        for topic_prefix,msgs in imdict.iteritems():
                            for msg in msgs:

                                imarr = np.fromstring(msg.data,dtype=np.uint8)
                                imarr.shape = (msg.height, msg.width)

                                result_images.append( (axis,bitno,flip,topic_prefix,imarr) )
                    else:
                        # average images
                        for topic_prefix,msgs in imdict.iteritems():
                            cum_images = []
                            for msg in msgs:

                                imarr = np.fromstring(msg.data,dtype=np.uint8)[:msg.height*msg.width]
                                imarr.shape = (msg.height, msg.width)
                                cum_images.append( imarr )
                            imarr = np.mean( np.array(cum_images,dtype=np.float), axis=0)
                            imarr = np.round(imarr).astype(np.uint8)
                            result_images.append( (axis,bitno,flip,topic_prefix,imarr) )

                    if save_pngs:
                        save_images('localize_axis%s_bits%02d_%d'%(axis,bitno,flip),imdict)
        output_data = {'images':result_images,
                       'display_width_height': (display_info['width'],display_info['height']) ,
                       'physical_display_id':physical_display_id,
                       'virtual_display_id':virtual_display_id,
                       }
        fd = open('images-%s-%s.pkl'%(physical_display_id,virtual_display_id),mode='w')
        pickle.dump(output_data,fd)
        fd.close()

def save_images(imname,imdict):
    for topic_prefix in imdict.keys():
        for i, msg in enumerate(imdict[topic_prefix]):
            fname = '%s_%s_%03d.png'%(imname,topic_prefix,i)
            arr = np.fromstring(msg.data,dtype=np.uint8)
            arr.shape = (msg.height, msg.width)

            pil_im = PIL.fromarray( arr[::-1] )
            pil_im.save(fname)

if __name__ == '__main__':

    parser = argparse.ArgumentParser()
    parser.add_argument(
        'topic_prefixes', type=str,
        help='a topic prefix of the images used to view the projector',
        nargs='*')

    parser.add_argument(
        '--physical_display_id', type=str)

    parser.add_argument(
        '--virtual_display_id', type=str)

    parser.add_argument(
        '--save_pngs', action='store_true', default=False)

    # use argparse, but only after ROS did its thing
    argv = rospy.myargv()
    args = parser.parse_args(argv[1:])
    # if len(args.topic_prefixes)==0:
    #     args.topic_prefixes.append('')

    localize_display( topic_prefixes=args.topic_prefixes,
                      physical_display_id = args.physical_display_id,
                      virtual_display_id = args.virtual_display_id,
                      save_pngs = args.save_pngs,
                      )