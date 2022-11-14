# end2end.py

from __future__ import division
import os
from copy import deepcopy
import warnings

warnings.filterwarnings("ignore")

# Torch imports
import torch
import torch.fft
import torch.nn as nn
import torch.optim as optim

# Numpy & Scipy imports
import numpy as np
import scipy.io

import cv2
# Local imports
from utils import to_var, to_data, spec_to_network_input
from models.model_components import maskCNNModel, classificationHybridModel, StudentMaskCNNModel
import torch.autograd.profiler as profiler
import time

SEED = 11

# Set the random seed manually for reproducibility.
np.random.seed(SEED)
torch.manual_seed(SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed(SEED)


def print_models(Model):
    """Prints model information for the generators and discriminators.
    """
    print("                 Model                ")
    print("---------------------------------------")
    print(Model)
    print("---------------------------------------")


def create_model(opts):
    """Builds the generators and discriminators.
    """

    maskCNN = maskCNNModel(opts)

    C_XtoY = classificationHybridModel(conv_dim_in=opts.y_image_channel,
                                       conv_dim_out=opts.n_classes,
                                       conv_dim_lstm=opts.conv_dim_lstm)

    if torch.cuda.is_available():
        maskCNN.cuda()
        C_XtoY.cuda()
        print('Models moved to GPU.')

    return maskCNN, C_XtoY


def checkpoint(iteration, mask_CNN, C_XtoY, opts):
    """Saves the parameters of both generators G_YtoX, G_XtoY and discriminators D_X, D_Y.
    """

    # mask_CNN_path = os.path.join(opts.checkpoint_dir, str(iteration) + '_maskCNN.pkl')
    mask_CNN_path = os.path.join(opts.checkpoint_dir, 'fuck' + '_maskCNN.pkl')
    
    torch.save(mask_CNN.state_dict(), mask_CNN_path)

    # C_XtoY_path = os.path.join(opts.checkpoint_dir, str(iteration) + '_C_XtoY.pkl')
    C_XtoY_path = os.path.join(opts.checkpoint_dir, 'fuck' + '_C_XtoY.pkl')


    torch.save(C_XtoY.state_dict(), C_XtoY_path)

def checkpoint_student(iteration, mask_CNN, C_XtoY, opts):
    """Saves the parameters of both generators G_YtoX, G_XtoY and discriminators D_X, D_Y.
    """

    # mask_CNN_path = os.path.join(opts.checkpoint_dir, str(iteration) + '_maskCNN.pkl')
    mask_CNN_path = os.path.join(opts.checkpoint_dir, 'student' + '_maskCNN.pkl')
    
    torch.save(mask_CNN.state_dict(), mask_CNN_path)

    # C_XtoY_path = os.path.join(opts.checkpoint_dir, str(iteration) + '_C_XtoY.pkl')
    C_XtoY_path = os.path.join(opts.checkpoint_dir, 'student' + '_C_XtoY.pkl')


    torch.save(C_XtoY.state_dict(), C_XtoY_path)

def load_checkpoint(opts):
    """Loads the generator and discriminator models from checkpoints.
    """

    maskCNN_path = os.path.join(opts.checkpoint_dir, str(opts.load_iters) + '_maskCNN.pkl')
    # import pdb
    
    maskCNN = maskCNNModel(opts)

    maskCNN.load_state_dict(torch.load(
        maskCNN_path, map_location=lambda storage, loc: storage),
        strict=False)

    C_XtoY_path = os.path.join(opts.checkpoint_dir, str(opts.load_iters) + '_C_XtoY.pkl')
    print(C_XtoY_path)
    C_XtoY = classificationHybridModel(conv_dim_in=opts.x_image_channel,
                                       conv_dim_out=opts.n_classes,
                                       conv_dim_lstm=opts.conv_dim_lstm)

    C_XtoY.load_state_dict(torch.load(
        C_XtoY_path, map_location=lambda storage, loc: storage),
        strict=False)

    if torch.cuda.is_available():
        maskCNN.cuda()
        C_XtoY.cuda()
        print('Models moved to GPU.')
    
    return maskCNN, C_XtoY

def load_teacher_model(opts):
    """Loads the generator and discriminator models from checkpoints.
    """

    # maskCNN_path = os.path.join(opts.checkpoint_dir, 'fuck' + '_maskCNN.pkl')
    maskCNN_path = os.path.join(opts.checkpoint_dir, str(opts.load_iters) + '_maskCNN.pkl')
    # import pdb
    
    maskCNN = maskCNNModel(opts)

    maskCNN.load_state_dict(torch.load(
        maskCNN_path, map_location=lambda storage, loc: storage),
        strict=False)

    # C_XtoY_path = os.path.join(opts.checkpoint_dir, 'fuck' + '_C_XtoY.pkl')
    C_XtoY_path = os.path.join(opts.checkpoint_dir, str(opts.load_iters) + '_C_XtoY.pkl')
    # print(C_XtoY_path)
    C_XtoY = classificationHybridModel(conv_dim_in=opts.x_image_channel,
                                       conv_dim_out=opts.n_classes,
                                       conv_dim_lstm=opts.conv_dim_lstm)

    C_XtoY.load_state_dict(torch.load(
        C_XtoY_path, map_location=lambda storage, loc: storage),
        strict=False)

    if torch.cuda.is_available():
        maskCNN.cuda()
        C_XtoY.cuda()
        print('Models moved to GPU.')
    
    return maskCNN, C_XtoY

def merge_images(sources, targets, batch_size, image_channel):
    """Creates a grid consisting of pairs of columns, where the first column in
    each pair contains images source images and the second column in each pair
    contains images generated by the CycleGAN from the corresponding images in
    the first column.
    """
    _, _, h, w = sources.shape
    row = int(np.sqrt(batch_size))
    column = int(batch_size / row)
    merged = np.zeros([image_channel, row * h, column * w * 2])
    for idx, (s, t) in enumerate(zip(sources, targets)):
        i = idx // column
        j = idx % column
        merged[:, i * h:(i + 1) * h, (j * 2) * w:(j * 2 + 1) * w] = s
        merged[:, i * h:(i + 1) * h, (j * 2 + 1) * w:(j * 2 + 2) * w] = t
    return merged.transpose(1, 2, 0)


def save_samples(iteration, fixed_Y, fixed_X, mask_CNN, opts):
    """Saves samples from both generators X->Y and Y->X.
    """
    fake_Y = mask_CNN(fixed_X)
    fixed_X = to_data(fixed_X)

    Y, fake_Y = to_data(fixed_Y), to_data(fake_Y)

    merged = merge_images(fixed_X, fake_Y, opts.batch_size, opts.y_image_channel)

    path = os.path.join(opts.sample_dir,
                        'sample-{:06d}-Y.png'.format(iteration))
    merged = np.abs(merged[:, :, 0] + 1j * merged[:, :, 1])
    merged = (merged - np.amin(merged)) / (np.amax(merged) - np.amin(merged)) * 255
    merged = cv2.flip(merged, 0)
    cv2.imwrite(path, merged)
    print('Saved {}'.format(path))


def save_samples_separate(iteration, fixed_Y, fixed_X, mask_CNN, opts,
                          name_X_test, labels_Y_test, saved_dir):
    """Saves samples from both generators X->Y and Y->X.
    """
    fake_Y = mask_CNN(fixed_X)

    fixed_Y, fake_Y, fixed_X = to_data(fixed_Y), to_data(fake_Y), to_data(fixed_X)

    for batch_index in range(opts.batch_size):
        if batch_index < len(name_X_test):
            path_src = os.path.join(saved_dir, name_X_test[batch_index])
            groundtruth_image = (
                np.squeeze(fixed_Y[batch_index, :, :, :]).transpose(1, 2, 0))

            groundtruth_image = np.abs(groundtruth_image[:, :, 0] + 1j * groundtruth_image[:, :, 1])
            groundtruth_image = (groundtruth_image - np.amin(groundtruth_image)) / (
                    np.amax(groundtruth_image) - np.amin(groundtruth_image)) * 255
            cv2.imwrite(path_src + '_groundtruth_' + str(iteration) + '.png', groundtruth_image)

            fake_image = (
                np.squeeze(fake_Y[batch_index, :, :, :]).transpose(1, 2, 0))
            fake_image = np.abs(fake_image[:, :, 0] + 1j * fake_image[:, :, 1])
            fake_image = (fake_image - np.amin(fake_image)) / (np.amax(fake_image) - np.amin(fake_image)) * 255
            cv2.imwrite(path_src + '_fake_' + str(iteration) + '.png', fake_image)

            raw_image = (
                np.squeeze(fixed_X[batch_index, :, :, :]).transpose(1, 2, 0))
            raw_image = np.abs(raw_image[:, :, 0] + 1j * raw_image[:, :, 1])
            raw_image = (raw_image - np.amin(raw_image)) / (np.amax(raw_image) - np.amin(raw_image)) * 255
            cv2.imwrite(path_src + '_raw_' + str(iteration) + '.png', raw_image)

    # print('Saved {}'.format(path))


def training_loop(training_dataloader_X, training_dataloader_Y, testing_dataloader_X,
                  testing_dataloader_Y, opts):
    """Runs the training loop.
        * Saves checkpoint every opts.checkpoint_every iterations
        * Saves generated samples every opts.sample_every iterations
    """
    loss_spec = torch.nn.MSELoss(reduction='mean')
    loss_class = nn.CrossEntropyLoss()
    # Create generators and discriminators
    if opts.load:
        mask_CNN, C_XtoY = load_checkpoint(opts)
    else:
        mask_CNN, C_XtoY = create_model(opts)

    g_params = list(mask_CNN.parameters()) + list(C_XtoY.parameters())
    g_optimizer = optim.Adam(g_params, opts.lr, [opts.beta1, opts.beta2])

    iter_X = iter(training_dataloader_X)
    iter_Y = iter(training_dataloader_Y)

    test_iter_X = iter(testing_dataloader_X)
    test_iter_Y = iter(testing_dataloader_Y)

    # Get some fixed data from domains X and Y for sampling. These are images that are held
    # constant throughout training, that allow us to inspect the model's performance.
    fixed_X, name_X_fixed = test_iter_X.next()
    fixed_X = to_var(fixed_X)

    fixed_Y, name_Y_fixed = test_iter_Y.next()
    fixed_Y = to_var(fixed_Y)
    # print("Fixed_X {}".format(fixed_X.shape))
    fixed_X_spectrum_raw = torch.stft(input=fixed_X, n_fft=opts.stft_nfft, hop_length=opts.stft_overlap,
                                      win_length=opts.stft_window, pad_mode='constant')
    fixed_X_spectrum = spec_to_network_input(fixed_X_spectrum_raw, opts)
    # print("Fixed {}".format(fixed_X_spectrum.shape))

    fixed_Y_spectrum_raw = torch.stft(input=fixed_Y, n_fft=opts.stft_nfft, hop_length=opts.stft_overlap,
                                      win_length=opts.stft_window, pad_mode='constant')
    fixed_Y_spectrum = spec_to_network_input(fixed_Y_spectrum_raw, opts)

    iter_per_epoch = min(len(iter_X), len(iter_Y))

    for iteration in range(1, opts.train_iters + 1):
        if iteration % iter_per_epoch == 0:
            iter_X = iter(training_dataloader_X)
            iter_Y = iter(training_dataloader_Y)

        images_X, name_X = iter_X.next()
        labels_X_mapping = list(
            map(lambda x: int(x.split('_')[5]), name_X))
        images_X, labels_X = to_var(images_X), to_var(
            torch.tensor(labels_X_mapping))
        images_Y, name_Y = iter_Y.next()
        labels_Y_mapping = list(
            map(lambda x: int(x.split('_')[5]), name_Y))
        images_Y, labels_Y = to_var(images_Y), to_var(
            torch.tensor(labels_Y_mapping))

        # ============================================
        #            TRAIN THE GENERATOR
        # ============================================

        images_X_spectrum_raw = torch.stft(input=images_X, n_fft=opts.stft_nfft, hop_length=opts.stft_overlap,

                                           win_length=opts.stft_window, pad_mode='constant');
        images_X_spectrum = spec_to_network_input(images_X_spectrum_raw, opts)

        images_Y_spectrum_raw = torch.stft(input=images_Y, n_fft=opts.stft_nfft, hop_length=opts.stft_overlap,
                                           win_length=opts.stft_window, pad_mode='constant');
        images_Y_spectrum = spec_to_network_input(images_Y_spectrum_raw, opts)
        #########################################
        ##    FILL THIS IN: X--Y               ##
        #########################################
        if iteration % 50 == 0:
            print("Iteration: {}/{}".format(iteration, opts.train_iters))
        fake_Y_spectrum = mask_CNN(images_X_spectrum)
        # 2. Compute the generator loss based on domain Y
        g_y_pix_loss = loss_spec(fake_Y_spectrum, images_Y_spectrum)
        labels_X_estimated = C_XtoY(fake_Y_spectrum)
        g_y_class_loss = loss_class(labels_X_estimated, labels_X)
        g_optimizer.zero_grad()
        G_Image_loss = opts.scaling_for_imaging_loss * g_y_pix_loss
        G_Class_loss = opts.scaling_for_classification_loss * g_y_class_loss
        G_Y_loss = G_Image_loss + G_Class_loss
        G_Y_loss.backward()
        g_optimizer.step()

        # Print the log info
        if iteration % opts.log_step == 0:
            print(
                'Iteration [{:5d}/{:5d}] | G_Y_loss: {:6.4f}| G_Image_loss: {:6.4f}| G_Class_loss: {:6.4f}'
                    .format(iteration, opts.train_iters,
                            G_Y_loss.item(),
                            G_Image_loss.item(),
                            G_Class_loss.item()))

        # Save the generated samples
        if (iteration % opts.sample_every == 0) and (not opts.server):
            # save_samples(iteration, fixed_Y_spectrum, fixed_X_spectrum, mask_CNN, opts)
            save_samples_separate(iteration, fixed_Y_spectrum, fixed_X_spectrum,
                                  mask_CNN, opts, name_X_fixed, name_Y_fixed, opts.sample_dir)

        # Save the model parameters
        if iteration % opts.checkpoint_every == 0:
            checkpoint(iteration, mask_CNN, C_XtoY, opts)

    test_iter_X = iter(testing_dataloader_X)
    test_iter_Y = iter(testing_dataloader_Y)
    iter_per_epoch_test = min(len(test_iter_X), len(test_iter_Y))

    error_matrix = np.zeros([len(opts.snr_list), 1], dtype=float)
    error_matrix_count = np.zeros([len(opts.snr_list), 1], dtype=int)

    error_matrix_info = []

    # iter_per_epoch_test = 500
    saved_data = {}
    for iteration in range(iter_per_epoch_test):
        images_X_test, name_X_test = test_iter_X.next()

        code_X_test_mapping = list(
            map(lambda x: float(x.split('_')[0]), name_X_test))

        snr_X_test_mapping = list(
            map(lambda x: int(x.split('_')[1]), name_X_test))

        instance_X_test_mapping = list(
            map(lambda x: int(x.split('_')[4]), name_X_test))

        labels_X_test_mapping = list(
            map(lambda x: int(x.split('_')[5]), name_X_test))

        images_X_test, labels_X_test = to_var(images_X_test), to_var(
            torch.tensor(labels_X_test_mapping))

        images_Y_test, labels_Y_test = test_iter_Y.next()
        images_Y_test = to_var(images_Y_test)

        images_X_test_spectrum_raw = torch.stft(input=images_X_test, n_fft=opts.stft_nfft,
                                                hop_length=opts.stft_overlap, win_length=opts.stft_window,
                                                pad_mode='constant');
        images_X_test_spectrum = spec_to_network_input(images_X_test_spectrum_raw, opts)

        images_Y_test_spectrum_raw = torch.stft(input=images_Y_test, n_fft=opts.stft_nfft,
                                                hop_length=opts.stft_overlap, win_length=opts.stft_window,
                                                pad_mode='constant');
        images_Y_test_spectrum = spec_to_network_input(images_Y_test_spectrum_raw, opts)
        fake_Y_test_spectrum = mask_CNN(images_X_test_spectrum)
        labels_X_estimated = C_XtoY(fake_Y_test_spectrum)
        saved_sample = to_data(labels_X_estimated)

        for i, label in enumerate(to_data(labels_X_test)):
            if label not in saved_data.keys():
                saved_data[label] = []
                saved_data[label].append(saved_sample[i])
            else:
                saved_data[label].append(saved_sample[i])
        _, labels_X_test_estimated = torch.max(labels_X_estimated, 1)

        test_right_case = (labels_X_test_estimated == labels_X_test)
        test_right_case = to_data(test_right_case)

        for batch_index in range(opts.batch_size):
            try:
                snr_index = opts.snr_list.index(snr_X_test_mapping[batch_index])
                error_matrix[snr_index] += test_right_case[batch_index]
                error_matrix_count[snr_index] += 1
                error_matrix_info.append([instance_X_test_mapping[batch_index], code_X_test_mapping[batch_index],
                                            snr_X_test_mapping[batch_index],
                                            labels_X_test_estimated[batch_index].cpu().data.int(),
                                            labels_X_test[batch_index].cpu().data.int()])
            except:
                print("Something else went wrong")
        if iteration % opts.log_step == 0:
            print('Testing Iteration [{:5d}/{:5d}]'
                  .format(iteration, iter_per_epoch_test))
    error_matrix = np.divide(error_matrix, error_matrix_count)
    error_matrix_info = np.array(error_matrix_info)
    scipy.io.savemat(
        opts.root_path + '/' + opts.dir_comment + '_' + str(opts.sf) + '_' + str(opts.bw) + '.mat',
        dict(error_matrix=error_matrix,
             error_matrix_count=error_matrix_count,
             error_matrix_info=error_matrix_info))

    with open('test.npy', 'wb') as f:
        np.save(f, saved_data)
        f.close()

def TS_train(training_dataloader_X, training_dataloader_Y, testing_dataloader_X,
                  testing_dataloader_Y, opts):
    """Runs the training loop.
        * Saves checkpoint every opts.checkpoint_every iterations
        * Saves generated samples every opts.sample_every iterations
    """
    distill_criterion = nn.CrossEntropyLoss()
    clf_criterion = nn.CrossEntropyLoss()
    loss_spec_student = torch.nn.MSELoss(reduction='mean')
    loss_class_student = nn.CrossEntropyLoss()
    loss_spec_regular = torch.nn.MSELoss(reduction='mean')
    loss_class_regular = nn.CrossEntropyLoss()
    # Create generators and discriminators
    if opts.load:
        mask_CNN_teacher, C_XtoY_teacher = load_checkpoint(opts)
    else:
        mask_CNN_teacher, C_XtoY_teacher = create_model(opts)

    mask_CNN_teacher, C_XtoY_teacher = load_teacher_model(opts)

    mask_CNN_student = StudentMaskCNNModel(opts)
    # C_XtoY_student = classificationHybridModel()
    C_XtoY_student = deepcopy(C_XtoY_teacher)

    maskCNN_path = os.path.join(opts.checkpoint_dir, str(opts.load_iters) + '_maskCNN.pkl')
    save_model = torch.load(maskCNN_path, map_location=lambda storage, loc: storage)
    model_dict = mask_CNN_student.state_dict()
    state_dict = {k:v for k,v in save_model.items() if k in model_dict.keys()}
    model_dict.update(state_dict)
    mask_CNN_student.load_state_dict(model_dict,
        strict=False)

    if torch.cuda.is_available():
        mask_CNN_student.cuda()
        C_XtoY_student.cuda()

    g_params = list(mask_CNN_student.parameters()) + list(C_XtoY_student.parameters())
    g_optimizer = optim.Adam(g_params, opts.lr, [opts.beta1, opts.beta2])

    iter_X = iter(training_dataloader_X)
    iter_Y = iter(training_dataloader_Y)

    test_iter_X = iter(testing_dataloader_X)
    test_iter_Y = iter(testing_dataloader_Y)

    # Get some fixed data from domains X and Y for sampling. These are images that are held
    # constant throughout training, that allow us to inspect the model's performance.
    fixed_X, name_X_fixed = test_iter_X.next()
    fixed_X = to_var(fixed_X)

    fixed_Y, name_Y_fixed = test_iter_Y.next()
    fixed_Y = to_var(fixed_Y)
    # print("Fixed_X {}".format(fixed_X.shape))
    fixed_X_spectrum_raw = torch.stft(input=fixed_X, n_fft=opts.stft_nfft, hop_length=opts.stft_overlap,
                                      win_length=opts.stft_window, pad_mode='constant')
    fixed_X_spectrum = spec_to_network_input(fixed_X_spectrum_raw, opts)
    # print("Fixed {}".format(fixed_X_spectrum.shape))

    fixed_Y_spectrum_raw = torch.stft(input=fixed_Y, n_fft=opts.stft_nfft, hop_length=opts.stft_overlap,
                                      win_length=opts.stft_window, pad_mode='constant')
    fixed_Y_spectrum = spec_to_network_input(fixed_Y_spectrum_raw, opts)

    iter_per_epoch = min(len(iter_X), len(iter_Y))

    for iteration in range(1, opts.train_iters + 1):
        if iteration % iter_per_epoch == 0:
            iter_X = iter(training_dataloader_X)
            iter_Y = iter(training_dataloader_Y)

        images_X, name_X = iter_X.next()
        labels_X_mapping = list(
            map(lambda x: int(x.split('_')[5]), name_X))
        images_X, labels_X = to_var(images_X), to_var(
            torch.tensor(labels_X_mapping))
        images_Y, name_Y = iter_Y.next()
        labels_Y_mapping = list(
            map(lambda x: int(x.split('_')[5]), name_Y))
        images_Y, labels_Y = to_var(images_Y), to_var(
            torch.tensor(labels_Y_mapping))

        # ============================================
        #            TRAIN THE GENERATOR
        # ============================================

        images_X_spectrum_raw = torch.stft(input=images_X, n_fft=opts.stft_nfft, hop_length=opts.stft_overlap,

                                           win_length=opts.stft_window, pad_mode='constant')
        images_X_spectrum = spec_to_network_input(images_X_spectrum_raw, opts) # shape: [16, 2, 128, 33]

        images_Y_spectrum_raw = torch.stft(input=images_Y, n_fft=opts.stft_nfft, hop_length=opts.stft_overlap,
                                           win_length=opts.stft_window, pad_mode='constant')
        images_Y_spectrum = spec_to_network_input(images_Y_spectrum_raw, opts)
        #########################################
        ##    FILL THIS IN: X--Y               ##
        #########################################
        if iteration % 50 == 0:
            print("Iteration: {}/{}".format(iteration, opts.train_iters))
        # regular losses for std model:
        fake_Y_spectrum_student = mask_CNN_student(images_X_spectrum)
        # fake_Y_spectrum_student = mask_CNN_teacher(images_X_spectrum)
        g_y_pix_loss_student = loss_spec_regular(fake_Y_spectrum_student, images_Y_spectrum)
        # 2. Compute the generator loss based on domain Y
        labels_X_estimated_student = C_XtoY_student(fake_Y_spectrum_student)
        g_y_class_loss_student = loss_class_regular(labels_X_estimated_student, labels_X)
        
        # distillation loss:
        fake_Y_spectrum_teacher = mask_CNN_teacher(images_X_spectrum) # shape: [16, 8, 33, 128]
        g_y_pix_loss_distill = loss_spec_student(fake_Y_spectrum_student, fake_Y_spectrum_teacher)
        g_y_class_loss_distill = loss_class_student(labels_X_estimated_student, C_XtoY_teacher(fake_Y_spectrum_teacher))

        g_optimizer.zero_grad()
        G_Image_loss = opts.scaling_for_imaging_loss * g_y_pix_loss_student
        G_Class_loss = opts.scaling_for_classification_loss * g_y_class_loss_student
        G_Y_loss = G_Image_loss + G_Class_loss + g_y_pix_loss_distill + g_y_class_loss_distill * 0
        G_Y_loss.backward()
        g_optimizer.step()

        # Print the log info
        if iteration % opts.log_step == 0:
            print(
                'Iteration [{:5d}/{:5d}] | G_Y_loss: {:6.4f}| G_Image_loss: {:6.4f}| G_Class_loss: {:6.4f} | GDist_Image_loss: {:6.4f} | GDist_Class_loss: {:6.4f}'
                    .format(iteration, opts.train_iters,
                            G_Y_loss.item(),
                            G_Image_loss.item(),
                            G_Class_loss.item(),
                            g_y_pix_loss_distill.item(),
                            g_y_class_loss_distill.item()))

        # Save the generated samples
        if (iteration % opts.sample_every == 0) and (not opts.server):
            # save_samples(iteration, fixed_Y_spectrum, fixed_X_spectrum, mask_CNN, opts)
            save_samples_separate(iteration, fixed_Y_spectrum, fixed_X_spectrum,
                                  mask_CNN_student, opts, name_X_fixed, name_Y_fixed, opts.sample_dir)

        # Save the model parameters
        if iteration % opts.checkpoint_every == 0:
            checkpoint_student(iteration, mask_CNN_student, C_XtoY_student, opts)

    test_iter_X = iter(testing_dataloader_X)
    test_iter_Y = iter(testing_dataloader_Y)
    iter_per_epoch_test = min(len(test_iter_X), len(test_iter_Y))

    error_matrix = np.zeros([len(opts.snr_list), 1], dtype=float)
    error_matrix_count = np.zeros([len(opts.snr_list), 1], dtype=int)

    error_matrix_info = []

    # iter_per_epoch_test = 500
    saved_data = {}
    for iteration in range(iter_per_epoch_test):
        images_X_test, name_X_test = test_iter_X.next()

        code_X_test_mapping = list(
            map(lambda x: float(x.split('_')[0]), name_X_test))

        snr_X_test_mapping = list(
            map(lambda x: int(x.split('_')[1]), name_X_test))

        instance_X_test_mapping = list(
            map(lambda x: int(x.split('_')[4]), name_X_test))

        labels_X_test_mapping = list(
            map(lambda x: int(x.split('_')[5]), name_X_test))

        images_X_test, labels_X_test = to_var(images_X_test), to_var(
            torch.tensor(labels_X_test_mapping))

        images_Y_test, labels_Y_test = test_iter_Y.next()
        images_Y_test = to_var(images_Y_test)

        images_X_test_spectrum_raw = torch.stft(input=images_X_test, n_fft=opts.stft_nfft,
                                                hop_length=opts.stft_overlap, win_length=opts.stft_window,
                                                pad_mode='constant')
        images_X_test_spectrum = spec_to_network_input(images_X_test_spectrum_raw, opts)

        images_Y_test_spectrum_raw = torch.stft(input=images_Y_test, n_fft=opts.stft_nfft,
                                                hop_length=opts.stft_overlap, win_length=opts.stft_window,
                                                pad_mode='constant')
        images_Y_test_spectrum = spec_to_network_input(images_Y_test_spectrum_raw, opts)
        fake_Y_test_spectrum = mask_CNN_student(images_X_test_spectrum)
        labels_X_estimated = C_XtoY_student(fake_Y_test_spectrum)
        saved_sample = to_data(labels_X_estimated)

        for i, label in enumerate(to_data(labels_X_test)):
            if label not in saved_data.keys():
                saved_data[label] = []
                saved_data[label].append(saved_sample[i])
            else:
                saved_data[label].append(saved_sample[i])
        _, labels_X_test_estimated = torch.max(labels_X_estimated, 1)

        test_right_case = (labels_X_test_estimated == labels_X_test)
        test_right_case = to_data(test_right_case)

        for batch_index in range(opts.batch_size):
            try:
                snr_index = opts.snr_list.index(snr_X_test_mapping[batch_index])
                error_matrix[snr_index] += test_right_case[batch_index]
                error_matrix_count[snr_index] += 1
                error_matrix_info.append([instance_X_test_mapping[batch_index], code_X_test_mapping[batch_index],
                                            snr_X_test_mapping[batch_index],
                                            labels_X_test_estimated[batch_index].cpu().data.int(),
                                            labels_X_test[batch_index].cpu().data.int()])
            except:
                print("Something else went wrong")
        if iteration % opts.log_step == 0:
            print('Testing Iteration [{:5d}/{:5d}]'
                  .format(iteration, iter_per_epoch_test))
    error_matrix = np.divide(error_matrix, error_matrix_count)
    error_matrix_info = np.array(error_matrix_info)
    scipy.io.savemat(
        opts.root_path + '/' + opts.dir_comment + '_student_' + str(opts.bw) + '.mat',
        dict(error_matrix=error_matrix,
             error_matrix_count=error_matrix_count,
             error_matrix_info=error_matrix_info))

    with open('test.npy', 'wb') as f:
        np.save(f, saved_data)
        f.close()
