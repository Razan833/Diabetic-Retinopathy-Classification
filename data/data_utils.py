import pandas as pd
import os

from torchvision import transforms
from datasets import Dataset

import random

import numpy as np
import torch
from torchvision import transforms
# from torch.utils.data import Dataset
# from datasets import Dataset
from PIL import Image, ImageFilter, ImageOps
from torchvision.transforms import functional as F

datasets_info = {"DDR": {"dataset_name": "DDR-dataset", "folder_prefix": "DR_grading"}}
dataset_root_dir = "local_datasets"

mean = [0.425753653049469, 0.29737451672554016, 0.21293757855892181]  # eyepacs mean
std = [0.27670302987098694, 0.20240527391433716, 0.1686241775751114]  # eyepacs std
data_aug = {
    'brightness': 0.4,
    'contrast': 0.4,
    'saturation': 0.2,
    'hue': 0.1,
    'scale': (0.08, 0.8),
    'degrees': (-180, 180),
}

class TwoCropTransform():
    def __init__(self, transform):
        self.transform = transform

    def __call__(self, x):
        return [self.transform(x), self.transform(x)]


class BYOLTransform():
    def __init__(self, transform_stu, transform_tea):
        self.transform_stu = transform_stu
        self.transform_tea = transform_tea

    def __call__(self, x1, x2):
        return [self.transform_stu(x1), self.transform_tea(x2)]


class GaussianBlur(object):
    """Gaussian blur augmentation from SimCLR: https://arxiv.org/abs/2002.05709"""

    def __init__(self, sigma=[.1, 2.]):
        self.sigma = sigma

    def __call__(self, x):
        sigma = random.uniform(self.sigma[0], self.sigma[1])
        x = x.filter(ImageFilter.GaussianBlur(radius=sigma))
        return x


class Solarize(object):
    """Solarize augmentation from BYOL: https://arxiv.org/abs/2006.07733"""

    def __call__(self, x):
        return ImageOps.solarize(x)

class TransformWithMask(object):
    def __init__(self, input_size, mean, std, data_aug, train_transfroms):
        scale = data_aug['scale']
        jitter_param = (data_aug['brightness'], data_aug['contrast'], data_aug['saturation'], data_aug['hue'])
        degree = data_aug['degrees']
        self.train_transforms = train_transfroms

        if train_transfroms:
            self.resized_crop = transforms.RandomResizedCrop(input_size, scale=scale)
            self.color_jitter = transforms.RandomApply([transforms.ColorJitter(*jitter_param)], p=0.8)
            self.grayscale = transforms.RandomGrayscale(p=0.2)
            self.gaussian_blur = transforms.RandomApply([GaussianBlur([.1, 2.])], p=1.0)
            self.rotation = transforms.RandomRotation(degree)
            self.p_rotation = 0.8
            self.p_hflip = 0.5
            self.p_vflip = 0.5
        else:
            self.resized = transforms.Resize(input_size)

        self.to_tensor = transforms.ToTensor()
        self.normalize = transforms.Normalize(mean, std)

    def __call__(self, img, mask):

        if self.train_transforms:
            img, mask = self.resized_crop_with_mask(self.resized_crop, img, mask)
            img = self.color_jitter(img)
            img = self.grayscale(img)
            img = self.gaussian_blur(img)
            img, mask = self.rotation_with_mask(self.rotation, img, mask, self.p_rotation)
            img, mask = self.horizontal_flip_with_mask(img, mask, self.p_hflip)
            img, mask = self.vertical_flip_with_mask(img, mask, self.p_vflip)
        else:
            img, mask = self.resized(img), self.resized(mask)

        img, mask = self.to_tensor(img), self.to_tensor(mask)
        img = self.normalize(img)

        return img, mask

    def resized_crop_with_mask(self, tf, img, mask):
        assert isinstance(tf, transforms.RandomResizedCrop)
        i, j, h, w = tf.get_params(img, tf.scale, tf.ratio)
        img = F.resized_crop(img, i, j, h, w, tf.size, tf.interpolation)
        mask = F.resized_crop(mask, i, j, h, w, tf.size, tf.interpolation)
        return img, mask

    def rotation_with_mask(self, tf, img, mask, p):
        assert isinstance(tf, transforms.RandomRotation)
        if random.random() < p:
            angle = tf.get_params(tf.degrees)
            img = F.rotate(img, angle, expand=tf.expand, center=tf.center, fill=tf.fill)
            mask = F.rotate(mask, angle, expand=tf.expand, center=tf.center, fill=tf.fill)
        return img, mask

    def horizontal_flip_with_mask(self, img, mask, p):
        if random.random() < p:
            img = F.hflip(img)
            mask = F.hflip(mask)
        return img, mask

    def vertical_flip_with_mask(self, img, mask, p):
        if random.random() < p:
            img = F.vflip(img)
            mask = F.vflip(mask)
        return img, mask


# Resample dataset to balance class distribution
def resample(_dataset, ratio = 3):
    # Calculate the size of minority class
    min_size = _dataset['label'].value_counts().min()

    #size of majority class
    max_size = _dataset['label'].value_counts().max()
    ratio = min(ratio, int(max_size/min_size))
    lst = []
    added_unique_rows = 0
    all_n_rows = 0

    # For each class, oversample/undersample to min_size * ratio
    for class_index, group in _dataset.groupby('label'):
        all_n_rows += len(group)
        if class_index == 0:
            # If class index is 0, sample with the specified ratio without replacement
            added_unique_rows += min_size*ratio
            lst.append(group.sample(min_size*ratio, replace=False))
        else:
            if len(group) > min_size*ratio:
                # If group size is larger than the desired size, sample without replacement
                added_unique_rows += min_size*ratio
                lst.append(group.sample(min_size*ratio, replace=False))
            else:
                # otherwise, sample with the replacement to reach the desired size
                
                added_unique_rows += len(group)
                lst.append(group)
                lst.append(group.sample(min_size*ratio-len(group), replace=True))

    # Concatenate the sampled subsets
    _dataset = pd.concat(lst)

    # Calculate and display the size of resampled classes
    for class_index, group in _dataset.groupby('label'):
        print(f'{class_index}: length: {len(group)}')

    # Display the count of instances per class and the ratio of added to the total rows
    print('N_added_rows: ', added_unique_rows)
    print('N_all_rows: ', all_n_rows)
    print('Ratio of used rows: ', added_unique_rows/all_n_rows)

    # Return the balanced dataset
    return _dataset


def pil_loader(img_path):
    with open(img_path, 'rb') as f:
        img = Image.open(f)
        return img.convert('RGB')

def npy_loader(mask_path):
    with open(mask_path, 'rb') as f:
        # import numpy as np
        img = np.load(f)
        return img

def get_func_transform(input_size, train_mode=True):
    def f_transform(examples):
        """
        The function is used to preprocess train dataset.
        """
        # pre-augmentation and preprocessing
        if train_mode:
            transform = TransformWithMask(input_size, mean, std, data_aug, train_transfroms=True)
        else:
            transform = TransformWithMask(input_size, mean, std, data_aug, train_transfroms=False)

        images = []
        masks = []
        
        for img_path, mask_path in zip(examples['image'], examples['mask_image']):
            img = pil_loader(img_path)
            mask = npy_loader(mask_path)
            mask = Image.fromarray(np.uint8(mask*255))
            img, mask = transform(img, mask)

            images.append(img)
            masks.append(mask)

        inputs = {}
        inputs['pixel_values'] = images
        inputs['mask'] = masks
        inputs['label'] = examples['label']
        
        return inputs
    
    return f_transform

# Define function to define collate function
def collate_fn(batch):
    return {
        'pixel_values': torch.stack([x['pixel_values'] for x in batch]),
        'masks': torch.stack([x['mask'] for x in batch]),
        'labels': torch.tensor([x['label'] for x in batch])
    }

def build_datasets(dataset_name, input_size=224):
    subset_names = ["test", "train", "valid"]
    subsets = []
    for subset_name in subset_names:
        image_folder = f'{dataset_root_dir}/{datasets_info[dataset_name]["dataset_name"]}/{datasets_info[dataset_name]["folder_prefix"]}_processed/{subset_name}'
        saliency_map_folder = f'{dataset_root_dir}/{datasets_info[dataset_name]["dataset_name"]}/{datasets_info[dataset_name]["folder_prefix"]}_saliency/{subset_name}'
        table_path = f'{dataset_root_dir}/{datasets_info[dataset_name]["dataset_name"]}/{datasets_info[dataset_name]["folder_prefix"]}/{subset_name}.csv'

        #load table
        labelsTable = pd.read_csv(table_path)

        labelsTable['image'] = labelsTable['image_path'].apply(lambda x: os.path.join(image_folder, x))
        labelsTable['mask_image'] = labelsTable['image_path'].apply(lambda x: os.path.join(saliency_map_folder, x.split('.')[0]+'.npy'))

        labelsTable = labelsTable.drop(columns=['image_path'], axis=1)

        # special for train subset
        if subset_name == "train":
            # resampling
            print("Train subset resampling ...")
            labelsTable = resample(labelsTable, ratio = 35)
            # random trainsforms with mask
            func_transform = get_func_transform(input_size, train_mode=True)
        else:
            func_transform = get_func_transform(input_size, train_mode=True)

        # to Dataset
        dataset = Dataset.from_pandas(labelsTable, preserve_index=False)

        # apply preprocessing
        preprocessed_dataset = dataset.with_transform(func_transform)
        subsets.append(preprocessed_dataset)

    return subsets[0], subsets[1], subsets[2]
