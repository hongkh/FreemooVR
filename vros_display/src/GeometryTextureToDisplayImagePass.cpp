/* -*- Mode: C++; tab-width: 4; indent-tabs-mode: t; c-basic-offset: 4 -*- */
#include "util.h"
#include "exrutil.h"
#include "GeometryTextureToDisplayImagePass.h"

#include <osgDB/ReadFile>
#include <osgDB/WriteFile>
#include <osgDB/FileUtils>

#include <sstream>

// Texture units
#define UNIT_GEOM 0
#define UNIT_P2G 1
#define UNIT_OUT 2

GeometryTextureToDisplayImagePass::GeometryTextureToDisplayImagePass(std::string shader_dir,
																	 osg::ref_ptr<osg::Texture2D> input_texture,
																	 std::string p2g_filename,
																	 bool show_geom_coords) :
	_input_texture(input_texture), _show_geom_coords(show_geom_coords)
{
	osg::ref_ptr<osg::Image> image = load_exr( p2g_filename, _display_width, _display_height);
	_p2g_texture = new osg::TextureRectangle;
	_p2g_texture->setTextureSize( _display_width, _display_height);
	_p2g_texture->setInternalFormat(GL_RGB32F);
	_p2g_texture->setFilter(osg::Texture2D::MIN_FILTER,osg::Texture2D::NEAREST);
	_p2g_texture->setFilter(osg::Texture2D::MAG_FILTER,osg::Texture2D::NEAREST);

	_p2g_texture->setImage(image);

	create_output_texture();
	_camera = new osg::Camera;
	setup_camera();
	osg::ref_ptr<osg::Group> g = create_input_geometry();
	_camera->addChild( g.get() );

	_top = new osg::Group;
	_top->addDescription("GeometryTextureToDisplayImagePass top node");
	_top->addChild( _camera );
	set_shader( join_path(shader_dir,"GeometryTextureToDisplayImagePass.vert"),
				join_path(shader_dir,"GeometryTextureToDisplayImagePass.frag") );

}

osg::ref_ptr<osg::Group> GeometryTextureToDisplayImagePass::create_input_geometry()
{
	osg::ref_ptr<osg::Group> top_group = new osg::Group;
	top_group->addDescription("GeometryTextureToDisplayImagePass input geometry top node");

    osg::ref_ptr<osg::Geode> geode = new osg::Geode;

	{
		float left=0.0;
		float bottom=0.0;
		float width=1.0;
		float height=1.0;
		float zpos=0.0;

		float max_tc_width= _p2g_texture->getTextureWidth();
		float max_tc_height= _p2g_texture->getTextureHeight();

		// make quad
		osg::Vec3Array* vertices = new osg::Vec3Array;
		osg::Vec2Array* tcs = new osg::Vec2Array;
		if (1) {
			// flip Y
			vertices->push_back(  osg::Vec3(left, bottom, zpos) ); tcs->push_back(osg::Vec2(0.0,max_tc_height));
			vertices->push_back(  osg::Vec3(left+width, bottom, zpos) ); tcs->push_back(osg::Vec2(max_tc_width,max_tc_height));
			vertices->push_back(  osg::Vec3(left+width, bottom+height, zpos) ); tcs->push_back(osg::Vec2(max_tc_width,0.0));
			vertices->push_back(  osg::Vec3(left, bottom+height, zpos) ); tcs->push_back(osg::Vec2(0.0,0.0));
		} else {
			vertices->push_back(  osg::Vec3(left, bottom, zpos) ); tcs->push_back(osg::Vec2(0.0,0.0));
			vertices->push_back(  osg::Vec3(left+width, bottom, zpos) ); tcs->push_back(osg::Vec2(max_tc_width,0.0));
			vertices->push_back(  osg::Vec3(left+width, bottom+height, zpos) ); tcs->push_back(osg::Vec2(max_tc_width,max_tc_height));
			vertices->push_back(  osg::Vec3(left, bottom+height, zpos) ); tcs->push_back(osg::Vec2(0.0,max_tc_height));
		}

		osg::ref_ptr<osg::Vec4Array> colors = new osg::Vec4Array;
		colors->push_back(osg::Vec4(1.0f,1.0f,1.0f,1.0f));

		osg::ref_ptr<osg::Geometry> this_geom = new osg::Geometry();
		this_geom->setVertexArray(vertices);
		this_geom->setTexCoordArray(0,tcs);
		this_geom->addPrimitiveSet(new osg::DrawArrays(osg::PrimitiveSet::QUADS,0,4));
		this_geom->setColorArray(colors.get());
		this_geom->setColorBinding(osg::Geometry::BIND_OVERALL);
		geode->addDrawable(this_geom);
	}

	_state_set = geode->getOrCreateStateSet();
    _state_set->setMode(GL_LIGHTING,osg::StateAttribute::OFF);
    _state_set->setTextureAttributeAndModes(UNIT_GEOM, _input_texture.get(), osg::StateAttribute::ON);
	_state_set->setTextureAttributeAndModes(UNIT_P2G, _p2g_texture.get(), osg::StateAttribute::ON);
	_state_set->setMode(GL_BLEND, osg::StateAttribute::ON);

    _state_set->addUniform(new osg::Uniform("inputGeometryTexture", UNIT_GEOM));
    _state_set->addUniform(new osg::Uniform("p2g", UNIT_P2G));
    _state_set->addUniform(new osg::Uniform("show_geom_coords", _show_geom_coords));

	top_group->addChild(geode.get());
	return top_group;
}

void GeometryTextureToDisplayImagePass::create_output_texture() {
	_out_texture = new osg::TextureRectangle;
	_out_texture->setDataVariance(osg::Object::DYNAMIC);
	_out_texture->setTextureSize(_display_width, _display_height);
	_out_texture->setInternalFormat(GL_RGBA);
	_out_texture->setFilter(osg::Texture2D::MIN_FILTER,osg::Texture2D::LINEAR);
	_out_texture->setFilter(osg::Texture2D::MAG_FILTER,osg::Texture2D::LINEAR);
}

void GeometryTextureToDisplayImagePass::setup_camera()
{
    // clearing
    _camera->setClearColor(osg::Vec4(0.0f,0.0f,0.0f,1.0f)); // black
    _camera->setClearMask(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);

    // projection and view
    _camera->setProjectionMatrix(osg::Matrix::ortho2D(0,1.0,0,1.0));
    _camera->setReferenceFrame(osg::Transform::ABSOLUTE_RF);
    _camera->setViewMatrix(osg::Matrix::identity());

    // viewport
    _camera->setViewport(0, 0, _display_width, _display_height);

	_camera->setRenderOrder(osg::Camera::PRE_RENDER);
    _camera->setRenderTargetImplementation(osg::Camera::FRAME_BUFFER_OBJECT);

    // attach the output texture
	_camera->attach(osg::Camera::COLOR_BUFFER, _out_texture.get(), 0);

}

void GeometryTextureToDisplayImagePass::set_shader(std::string vert_filename, std::string frag_filename)
{
    osg::ref_ptr<osg::Shader> vshader = new osg::Shader( osg::Shader::VERTEX );
	{
		std::string fqFileName = osgDB::findDataFile(vert_filename);
		if( fqFileName.length() == 0 )
			{
				std::stringstream ss;
				ss << "File \"" << vert_filename << "\" not found.";
				throw std::ios_base::failure(ss.str());
			}
		vshader->loadShaderSourceFromFile(fqFileName);
	}

    osg::ref_ptr<osg::Shader> fshader = new osg::Shader( osg::Shader::FRAGMENT );
	{
		std::string fqFileName = osgDB::findDataFile(frag_filename);
		if( fqFileName.length() == 0 )
			{
				std::stringstream ss;
				ss << "File \"" << frag_filename << "\" not found.";
				throw std::ios_base::failure(ss.str());
			}
		fshader->loadShaderSourceFromFile(fqFileName);
	}

    _program = new osg::Program;

    _program->addShader(vshader.get());
    _program->addShader(fshader.get());
	_program->addBindFragDataLocation( "MyFragColor", 0);
    _state_set->setAttributeAndModes(_program.get(), osg::StateAttribute::ON);// | osg::StateAttribute::OVERRIDE );
}