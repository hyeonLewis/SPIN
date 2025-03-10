from dataclasses import astuple
import os
import sys
from typing import overload
import torch
from torchvision.utils import make_grid
import numpy as np
import cv2
import pytorch3d
sys.path.append(os.path.abspath(''))
os.environ["CUB_HOME"] = os.getcwd() + "/cub-1.10.0"

# Data structures and functions for rendering
from pytorch3d.structures import Meshes
from pytorch3d.renderer import (
    PerspectiveCameras, 
    PointLights, 
    Materials, 
    RasterizationSettings, 
    MeshRenderer, 
    MeshRasterizer,  
    SoftPhongShader,
    TexturesVertex
)

class Renderer:
    def __init__(self, focal_length = 5000.0, img_res=224, *args, faces):
        self.focal_length = ((focal_length, focal_length),)
        self.camera_center = ((img_res // 2, img_res // 2),)
        self.img_res = img_res
        self.faces = faces
        #Below znear and zfar are constant used in pyrender
        self.znear = 0.05
        self.zfar = 100.0

    def visualize_mesh(self, vertices, camera_translation, images):
        device = torch.device("cuda:0")
        vertices = vertices.to(device)
        camera_translation = camera_translation.to(device)

        images_cpu = images.cpu()
        images_cpu = np.transpose(images_cpu.numpy(), (0, 2, 3, 1)) #(B, H, W, C)

        rend_imgs = []

        for i in range(vertices.shape[0]):
            rend_img = (self.__call__(vertices[i], camera_translation[i], device)).float() #returns [1, 224, 224, 4]
            rend_img = rend_img[0, ... , :3] #[224, 224, 3]
            rend_img_cpu = rend_img.cpu() 
            rend_img = (cv2.rotate(rend_img_cpu.numpy(), cv2.ROTATE_180)) 
            rend_img = self.overlay_img(rend_img, images_cpu[i], device) 
            rend_img = torch.transpose(rend_img, 0, 2)
            rend_img = torch.transpose(rend_img, 1, 2)
            rend_imgs.append(images[i]) 
            rend_imgs.append(rend_img)

        rend_imgs = make_grid(rend_imgs, nrow=2)
        return rend_imgs

    #Overlay mesh and image using depth mask
    def overlay_img(self, rend_img, img, device): 
        mask = (rend_img == 1)[:,:,:,None]
        mask = torch.from_numpy(mask).squeeze()
        mask = mask.cpu().numpy()
        output = rend_img[:,:,:3] * ~mask + mask * img
        
        return torch.from_numpy(output).to(device)
    
    def __call__(self, vertices, camera_translation, device):
        R, T = torch.from_numpy(np.eye(3)).unsqueeze(dim = 0), camera_translation.reshape(1, 3)

        cameras = PerspectiveCameras(device = device, focal_length = self.focal_length, principal_point=self.camera_center, R = R, T = T, image_size=((self.img_res, self.img_res),), in_ndc=False)

        raster_settings = RasterizationSettings(
            image_size=self.img_res, 
            blur_radius=0.0, 
        )

        lights = PointLights(device=device, location=[[5, 5, -5]]) 

        renderer = MeshRenderer(
            rasterizer = MeshRasterizer(
                cameras = cameras,
                raster_settings=raster_settings
            ),
            shader=SoftPhongShader(
                device = device,
                cameras=cameras,
                lights=lights
            )
        )

        verts_rgb = torch.ones_like(vertices)[None]
        textures = TexturesVertex(verts_features=verts_rgb.to(device))

        vertices = vertices.reshape(-1, vertices.shape[0], vertices.shape[1])
        faces = torch.from_numpy(self.faces.astype(np.float32))
        faces = faces.unsqueeze(dim = 0).to(device)

        mesh = Meshes(
            verts = vertices,
            faces = faces,
            textures = textures
        )

        return renderer(mesh, cameras = cameras, lights = lights)

