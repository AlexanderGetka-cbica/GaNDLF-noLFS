import torch
from torch.utils.data.dataset import Dataset
import numpy as np
import pandas as pd
from torch.utils.data import DataLoader
import os
import random
import random
import scipy
import torchio
from torchio.transforms import *
from torchio import Image, Subject

## todo: ability to change interpolation type from config file
## todo: ability to change the dimensionality according to the config file
# define individual functions/lambdas for augmentations to handle properties
def mri_artifact(p = 1):
    return OneOf({RandomMotion(): 0.5, RandomGhosting(): 0.5,}, p=p)

def spatial_transform(p=1):
    return OneOf({RandomMotion(): 0.5, RandomGhosting(): 0.5}, p=p)

def bias(p=1):
    return RandomBiasField(coefficients = 0.5, order= 3, p= p, seed = None)

def blur(p=1):
    return RandomBlur(std = (0., 4.), p = p, seed = None)

def noise(p=1):
    return RandomNoise(mean = 0, std = (0, 0.25), p = p, seed = None)

def swap(p=1):
    return RandomSwap(patch_size = 15, num_iterations = 100, p = p, seed = None) 

# Defining a dictionary - key is the string and the value is the augmentation object
global_augs_dict = {
    'normalize':ZNormalization(),
    'spatial': spatial_transform,
    'kspace': mri_artifact,
    'bias': bias,
    'blur': blur,
    'noise': noise,
    'swap': swap
}

# This function takes in a dataframe, with some other parameters and returns the dataloader
def ImagesFromDataFrame(dataframe, psize, channelHeaders, labelHeader, q_max_length, q_samples_per_volume, q_num_workers, q_verbose, train = True, augmentations = None):
    # Finding the dimension of the dataframe for computational purposes later
    num_row, num_col = dataframe.shape
    # num_channels = num_col - 1 # for non-segmentation tasks, this might be different
    # changing the column indices to make it easier
    dataframe.columns = range(0,num_col)
    dataframe.index = range(0,num_row)
    # This list will later contain the list of subjects 
    subjects_list = []

    # iterating through the dataframe
    for patient in range(num_row):
        # We need this dict for storing the meta data for each subject such as different image modalities, labels, any other data
        subject_dict = {}
        # iterating through the channels/modalities/timepoints of the subject
        for channel in channelHeaders:
            # assigning the dict key to the channel
            subject_dict[str(channel)] = Image(str(dataframe[channel][patient]),type = torchio.INTENSITY)
        if labelHeader is not None:
            subject_dict['label'] = Image(str(dataframe[labelHeader][patient]),type = torchio.LABEL)
            if not train:
                subject_dict['path_to_metadata'] = str(dataframe[labelHeader][patient])
        else:
            subject_dict['label'] = "NA"
            if not train:
                subject_dict['path_to_metadata'] = str(dataframe[channel][patient])
        # Initializing the subject object using the dict
        subject = Subject(subject_dict) 
        # Appending this subject to the list of subjects
        subjects_list.append(subject)
    
    augmentation_list = []
    
    # first, we want to do the resampling, if it is present - required for inference as well
    if 'resample' in augmentations:
        if 'resolution' in augmentations['resample']:
            # resample_split = str(aug).split(':')
            resample_values = tuple(np.array(augmentations['resample']['resolution']).astype(np.float))
            augmentation_list.append(Resample(resample_values))
    
    # next, we want to do the intensity normalize - required for inference as well
    if 'normalize' in augmentations:
        augmentation_list.append(global_augs_dict['normalize'])
    
    # other augmentations should only happen for training - and also setting the probabilities for the augmentations
    if train:
        for aug in augmentations:
            if (aug != 'normalize') and (aug != 'resample'): # resample and normalize should always have probability=1
                actual_function = global_augs_dict[aug](p=augmentations[aug]['probability'])
                augmentation_list.append(actual_function)
        
    transform = Compose(augmentation_list)
    
    subjects_dataset = torchio.ImagesDataset(subjects_list, transform=transform)

    if not train:
        return subjects_dataset

    sampler = torchio.data.UniformSampler(psize) 
    # all of these need to be read from model.yaml
    patches_queue = torchio.Queue(subjects_dataset,max_length=q_max_length, samples_per_volume=q_samples_per_volume, sampler=sampler, num_workers=q_num_workers, shuffle_subjects=False, shuffle_patches=True, verbose=q_verbose) 

    
    return patches_queue
