import os
from os import listdir
from os.path import isfile, join
from random import random
from PIL import Image
import argparse
from tqdm import tqdm
import numpy as np
import cv2

#args
# randomize training/test (across augmentation also)
# rotation
# simplify tracing
# output_format rgb, g
# output_size [w, h] or keep the same
# crops/centers
#  - to crop or to hard-resize
# duplication + augmentation (sheer, rotate, etc)
# output save format (jpg png)



parser = argparse.ArgumentParser()

# input, output
parser.add_argument("--input_dir", help="where to get input images")
parser.add_argument("--output_dir", help="where to put output images")

# processing action
parser.add_argument("--action", type=str, help="which actions {colorize,trace}", required=True, choices=['colorize', 'trace'], default="")

# augmentation
parser.add_argument("--augment", type=bool, default=False, help="to augment or not augment")
parser.add_argument("--num", type=int, help="number of regions to output", default=64)
parser.add_argument("--frac", type=float, help="cropping ratio before resizing", default=0.6667)
parser.add_argument("--w", type=int, help="output image width", default=64)
parser.add_argument("--h", type=int, help="output image height", default=64)
parser.add_argument("--max_ang", type=float, help="max rotation angle (radians)", default=0)

# augmentation
parser.add_argument("--split", type=bool, default=False, help="to split into training/test")
parser.add_argument("--pct_train", type=float, default=0.9, help="percentage that goes to training set")
parser.add_argument("--combine", type=bool, default=False, help="concatenate input and output images (like for training pix2pix)")



def cv2pil(img):
    if len(img.shape) == 2:
        cv2_im = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
    else:
        cv2_im = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    pil_im = Image.fromarray(cv2_im)
    return pil_im


def posterize(im, n):
    indices = np.arange(0,256)   # List of all colors 
    divider = np.linspace(0,255,n+1)[1] # we get a divider
    quantiz = np.int0(np.linspace(0,255,n)) # we get quantization colors
    color_levels = np.clip(np.int0(indices/divider),0,n-1) # color levels 0,1,2..
    palette = quantiz[color_levels] # Creating the palette
    im2 = palette[im]  # Applying palette on image
    im2 = cv2.convertScaleAbs(im2) # Converting image back to uint8
    return im2



def canny(im1):
    im2 = cv2.GaussianBlur(im1, (5, 5), 0)
    im2 = cv2.GaussianBlur(im2, (3, 3), 0)
    im2 = cv2.Canny(im2, 100, 200)
    im2 = cv2.HoughLines(im2, 1, pi / 180, 70)
#    im2 = cv2.dilate(im2, (5, 5))
#    im2 = cv2.dilate(im2, (3, 3))
    im2 = cv2.cvtColor(im2, cv2.COLOR_GRAY2RGB)
    return im2









# colorization
def image2colorlabels(img, colors):
    h, w = img.height, img.width
    pixels = np.array(list(img.getdata()))
    dists = np.array([np.sum(np.abs(pixels-c), axis=1) for c in colors])
    classes = np.argmin(dists, axis=0)

def colorize_labels(img, colors):
    h, w = img.height, img.width
    classes = image2colorlabels(img)
    img = Image.fromarray(np.uint8(classes.reshape((h, w, 3))))
    return img
    
def colorize_colors(img, colors):
    h, w = img.height, img.width
    classes = image2colorlabels(img)
    pixels_clr = np.array([colors[p] for p in classes]).reshape((h, w, 3))
    img = Image.fromarray(np.uint8(pixels_clr))
    return img


def pil2cv(img):
    pil_image = img.convert('RGB') 
    cv2_image = np.array(pil_image) 
    cv2_image = cv2_image[:, :, ::-1].copy()
    return cv2_image
    
# tracing
def trace(img):
    img = pil2cv(img)
    #im2 = posterize(img, 8)
    im2 = cv2.GaussianBlur(img, (5, 5), 0)
    im2 = cv2.GaussianBlur(im2, (3, 3), 0)
    im3 = cv2.cvtColor(im2, cv2.COLOR_RGB2GRAY)
    ret, im4 = cv2.threshold(im3, 127, 255, 0)
    ret, img = cv2.threshold(im3, 255, 255, 0)
    im5, contours, hierarchy = cv2.findContours(im4, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    contours = [ c for c in contours if cv2.arcLength(c, True) > 100 ] #and cv2.contourArea(c) > 10]
    for contour in contours:
        cv2.drawContours(img, [contour], 0, (255), 2)
    img = cv2pil(img)
    return img
    

    

def crop_rot_resize(img, img0, frac, w2, h2, ang):
    ar = float(w2 / h2)
    h1, w1 = img.height, img.width
    if float(w1 / h1) > ar:
        h1_crop = max(h2, h1 * frac)
        w1_crop = h1_crop * ar
    else:
        w1_crop = max(w2, w1 * frac)
        h1_crop = w1_crop / ar
    x_crop, y_crop = (w1 - w1_crop - 1) * random(), (h1 - h1_crop - 1) * random()
    h1_crop, w1_crop, y_crop, x_crop = int(h1_crop), int(w1_crop), int(y_crop), int(x_crop)
    img_crop = img.crop((x_crop, y_crop, x_crop+w1_crop, y_crop+h1_crop))
    img0_crop = img0.crop((x_crop, y_crop, x_crop+w1_crop, y_crop+h1_crop))
    img = img_crop.resize((w2, h2), Image.BICUBIC)
    img0 = img0_crop.resize((w2, h2), Image.BICUBIC)
    return img, img0


# augmentation
def augmentation(img, img0, args):
    num, w2, h2, frac, max_ang = args.num, args.w, args.h, args.frac, args.max_ang
    ang = max_ang * (-1 + 2 * random())
    aug_imgs, aug_img0s = [], []
    for n in range(num):
        aug_img, aug_img0 = crop_rot_resize(img, img0, frac, w2, h2, ang)
        aug_imgs.append(aug_img)
        aug_img0s.append(aug_img0)
    return aug_imgs, aug_img0s
    
# main program    
def main(args):
    action, augment, split, combine = args.action, args.augment, args.split, args.combine

    # make output dir(s)
    input_dir, output_dir = args.input_dir, args.output_dir
    if not os.path.isdir(output_dir):
        os.mkdir(output_dir)
    if split and not os.path.isdir(join(output_dir,'train')):
        os.mkdir(join(output_dir,'train'))
    if split and not os.path.isdir(join(output_dir,'test')):
        os.mkdir(join(output_dir,'test'))
    
    # cycle through input images
    images = [f for f in listdir(input_dir) if isfile(join(input_dir, f)) ][0:10]

    # if to split into training/test flders
    training = [1] * len(images)
    if split:
        n_train = int(len(images) * args.pct_train)
        training[n_train:] = [0] * (len(images) - n_train)
    
    for img_idx, img_path in enumerate(tqdm(images)):
        #try:
        # open image
        img0 = Image.open(join(input_dir, img_path)).convert("RGB")
        img = Image.open(join(input_dir, img_path)).convert("RGB")#img0
    
        if action == 'colorize':
            #colors = [[0,255,0], [0,0,0], [255,0,0], [255, 255, 255], [0, 0, 255], [255, 255, 0], [0, 255, 255]]
            colors = [[255,255,255], [0,0,0], [127,0,0], [0, 0, 127], [0, 127, 0]]
            img = colorize_colors(img)

        elif action == 'trace':
            img = trace(img)

        imgs, imgs0 = [], []
        if augment:
            imgs, imgs0 = augmentation(img, img0, args)
        else:
            imgs, imgs0 = [img], [img0]
        
        for i, (img0, img1) in enumerate(zip(imgs, imgs0)):
            if combine:
                img_f = Image.new('RGB', (args.w * 2, args.h)) 
#                img_f = np.concatenate([img0, img1], axis=1)
                img_f.paste(img0, (0, 0))
                img_f.paste(img1, (args.w, 0))
                out_dir = join(output_dir, 'train' if training[img_idx]==1 else 'test') if split else output_dir
                img_f.save(join(out_dir, img_path[0:-5]+"_%d.png"%i))
#            img1.save(join(output_dir, img_path[0:-5]+"_x%d.png"%i))
#            img0.save(join(output_dir, img_path[0:-5]+"_y%d.png"%i))
        
#        img.save(join(output_dir, img_path2))
#        img0.save(join(output_dir, img_path[0:-5]+"_y.png"))
        
#        cv2.imwrite(join(output_dir, img_path), img)
        #im1 = cv2.imread(join(input_dir, img_path))
        #im2 = crop_resize(im1, frac, w2, h2)
#        im2 = contour(im1)
        #im2 = posterize(im1, 8)
        #cv2.imwrite(join(output_dir, img_path), im2)
        #cv2.imwrite(join(output_dir, img_path2), im1)
#            im2 = convert_image(im1)
#            img_path2 = img_path[0:-5]+"_y.png"
#            im1.save(join(output_dir, img_path))
#            im2.save(join(output_dir, img_path2))

#        except:
#            print('error...')

if __name__ == '__main__':
    args = parser.parse_args()
    main(args)
